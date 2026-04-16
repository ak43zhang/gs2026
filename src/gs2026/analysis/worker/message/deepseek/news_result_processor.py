"""新闻 AI 分析结果处理器 —— 拆分 JSON、结构化入库、写入 Redis 缓存。

核心职责:
    1. 将 DeepSeek 返回的批量 JSON（15-18 条合并）拆分为单条记录
    2. 结构化字段写入 MySQL  analysis_news_detail_2026
    3. 同步写入 Redis 缓存（详情 + 时间线 + 类型索引 + 评分排行）
    4. 更新 Redis 统计信息

依赖:
    - gs2026.utils: mysql_util, config_util, redis_util, log_util
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, log_util, mysql_util as mu
from gs2026.utils import redis_util

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 配置
url: str = config_util.get_config('common.url')
if not url:
    # 回退到 mysql 配置手动构建
    mysql_host = config_util.get_config('mysql.host', '192.168.0.101')
    mysql_port = config_util.get_config('mysql.port', 3306)
    mysql_user = config_util.get_config('mysql.user', 'root')
    mysql_password = config_util.get_config('mysql.password', '123456')
    mysql_database = config_util.get_config('mysql.database', 'gs')
    url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}?charset=utf8"
    logger.warning(f"common.url 未配置，使用手动构建的 URL: {url}")

redis_host: str = config_util.get_config('common.redis.host', 'localhost')
redis_port: int = int(config_util.get_config('common.redis.port', 6379))

logger.info(f"NewsResultProcessor 初始化: url={url[:50]}..., redis={redis_host}:{redis_port}")

mysql_tool = mu.get_mysql_tool(url)
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# Redis 缓存 TTL（秒）
DETAIL_TTL = 48 * 3600      # 单条新闻 48 小时
TIMELINE_TTL = 72 * 3600    # 时间线 72 小时
LATEST_MAX = 200             # 最新列表最大长度


def _ensure_redis():
    """确保 Redis 已初始化"""
    try:
        redis_util._get_redis_client()
    except RuntimeError:
        redis_util.init_redis(host=redis_host, port=int(redis_port), decode_responses=False)


def _safe_int(val: Any, default: int = 0) -> int:
    """安全转换为 int"""
    if val is None:
        return default
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def _safe_str(val: Any, default: str = '') -> str:
    """安全转换为 str"""
    if val is None:
        return default
    return str(val).strip()


def _safe_json_list(val: Any) -> str:
    """将列表值安全转换为 JSON 字符串"""
    if val is None:
        return '[]'
    if isinstance(val, str):
        # 可能是逗号分隔的字符串
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass
        # 逗号分隔
        items = [v.strip() for v in val.split(',') if v.strip()]
        return json.dumps(items, ensure_ascii=False)
    if isinstance(val, list):
        return json.dumps(val, ensure_ascii=False)
    return '[]'


def _map_news_size(composite_score: int) -> str:
    """根据综合评分计算消息大小"""
    if composite_score >= 90:
        return '重大'
    elif composite_score >= 60:
        return '大'
    elif composite_score >= 30:
        return '中'
    else:
        return '小'


def _map_news_type(val: str) -> str:
    """标准化消息类型到 ENUM 允许值"""
    val = _safe_str(val, '中性')
    if '利好' in val:
        return '利好'
    elif '利空' in val:
        return '利空'
    else:
        return '中性'


def _get_news_info(content_hash: str, source_table: str) -> Dict[str, str]:
    """从原始新闻表查询标题、内容、发布时间、出处
    
    注意：不同新闻表的列名和顺序可能不同：
    - news_cls2026: 内容,发布时间,标题,内容hash,出处,analysis
    - news_combine2026: 标题,发布时间,内容,出处,内容hash,analysis
    """
    if not content_hash or not source_table:
        logger.warning(f"_get_news_info: content_hash 或 source_table 为空")
        return {'标题': '', '内容': '', '发布时间': '', '出处': ''}
    
    # 清理输入，防止 SQL 注入
    safe_hash = content_hash.replace("'", "\\'").replace("\\", "\\\\")
    safe_table = ''.join(c for c in source_table if c.isalnum() or c == '_')
    
    try:
        # 使用原生 SQL（避免参数绑定兼容性问题）
        sql = f"SELECT `标题`,`内容`,`发布时间`,`出处` FROM `{safe_table}` WHERE `内容hash`='{safe_hash}' LIMIT 1"
        logger.debug(f"查询 SQL: {sql[:100]}...")
        
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
            logger.debug(f"查询结果行数: {len(df)}")
            
            if not df.empty:
                row = df.iloc[0]
                result = {
                    '标题': _safe_str(row.get('标题', '')),
                    '内容': _safe_str(row.get('内容', '')),
                    '发布时间': _safe_str(row.get('发布时间', '')),
                    '出处': _safe_str(row.get('出处', '')),
                }
                logger.debug(f"查询成功: 标题={result['标题'][:30]}...")
                return result
            else:
                logger.warning(f"未找到记录: hash={content_hash[:20]}..., table={source_table}")
    except Exception as e:
        logger.error(f"查询原始新闻失败 hash={content_hash[:20]}..., table={source_table}: {e}", exc_info=True)
    
    return {'标题': '', '内容': '', '发布时间': '', '出处': ''}


def _parse_publish_time(time_str: str) -> Optional[str]:
    """解析发布时间为 MySQL DATETIME 格式"""
    if not time_str:
        return None
    # 尝试常见格式
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            dt = datetime.strptime(time_str.strip(), fmt)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return time_str[:19] if len(time_str) >= 19 else None


def extract_record(msg: dict, source_table: str, version: str) -> Dict[str, Any]:
    """从单条消息 JSON 提取结构化字段

    Args:
        msg: AI 分析结果中的单条消息字典
        source_table: 来源表名
        version: 分析版本

    Returns:
        结构化字段字典
    """
    content_hash = _safe_str(msg.get('消息id', ''))
    if not content_hash:
        return {}

    # 从原始表获取冗余字段
    news_info = _get_news_info(content_hash, source_table)

    importance = _safe_int(msg.get('重要程度评分', 0))
    biz_impact = _safe_int(msg.get('业务影响维度评分', 0))
    
    # 【修复】强制按公式计算综合评分：重要程度评分×4 + 业务影响维度评分
    composite = importance * 4 + biz_impact
    
    # 【修复】强制根据计算后的综合评分计算消息大小，忽略AI返回的消息大小和综合评分
    news_size = _map_news_size(composite)

    news_type = _map_news_type(msg.get('消息类型', '中性'))

    publish_time = _parse_publish_time(news_info.get('发布时间', ''))

    return {
        'content_hash': content_hash,
        'source_table': source_table,
        'title': news_info.get('标题', '')[:500],
        'content': news_info.get('内容', ''),
        'publish_time': publish_time,
        'source': news_info.get('出处', '')[:64],
        'importance_score': max(-128, min(127, importance)),
        'business_impact_score': max(-32768, min(32767, biz_impact)),
        'composite_score': max(-32768, min(32767, composite)),
        'news_size': news_size,
        'news_type': news_type,
        'sectors': _safe_json_list(msg.get('涉及板块')),
        'concepts': _safe_json_list(msg.get('涉及概念')),
        'leading_stocks': _safe_json_list(msg.get('龙头个股')),
        'sector_details': json.dumps(msg.get('板块详情', []), ensure_ascii=False),
        'analysis_version': version,
    }


def save_to_mysql(record: Dict[str, Any]) -> bool:
    """将单条记录写入 MySQL（INSERT ON DUPLICATE KEY UPDATE）

    Args:
        record: extract_record 返回的结构化字段字典

    Returns:
        是否写入成功
    """
    if not record or not record.get('content_hash'):
        return False

    try:
        # 转义单引号
        def esc(val):
            if val is None:
                return 'NULL'
            s = str(val).replace("'", "\\'").replace("\\", "\\\\")
            return f"'{s}'"

        publish_time_sql = esc(record['publish_time']) if record['publish_time'] else 'NULL'

        sql = f"""INSERT INTO analysis_news_detail_2026 
            (content_hash, source_table, title, content, publish_time, source,
             importance_score, business_impact_score, composite_score,
             news_size, news_type, sectors, concepts, leading_stocks, sector_details,
             analysis_version, analysis_time)
            VALUES (
                {esc(record['content_hash'])}, {esc(record['source_table'])},
                {esc(record['title'])}, {esc(record['content'])},
                {publish_time_sql}, {esc(record['source'])},
                {record['importance_score']}, {record['business_impact_score']}, {record['composite_score']},
                {esc(record['news_size'])}, {esc(record['news_type'])},
                {esc(record['sectors'])}, {esc(record['concepts'])},
                {esc(record['leading_stocks'])}, {esc(record['sector_details'])},
                {esc(record['analysis_version'])}, NOW()
            )
            ON DUPLICATE KEY UPDATE
                importance_score = VALUES(importance_score),
                business_impact_score = VALUES(business_impact_score),
                composite_score = VALUES(composite_score),
                news_size = VALUES(news_size),
                news_type = VALUES(news_type),
                sectors = VALUES(sectors),
                concepts = VALUES(concepts),
                leading_stocks = VALUES(leading_stocks),
                sector_details = VALUES(sector_details),
                analysis_version = VALUES(analysis_version),
                analysis_time = NOW()"""

        mysql_tool.update_data(sql)
        return True
    except Exception as e:
        logger.error(f"MySQL 写入失败 {record.get('content_hash', '?')}: {e}")
        return False


def save_to_redis(record: Dict[str, Any]) -> bool:
    """将单条记录写入 Redis 缓存

    写入内容:
        1. news:detail:{hash}       → Hash（完整数据）
        2. news:timeline:{date}     → Sorted Set（score=时间戳）
        3. news:type:{date}:{type}  → Sorted Set（按类型分组）
        4. news:top:{date}          → Sorted Set（score=综合评分）
        5. news:latest              → List（最新N条）
        6. news:stats:{date}        → Hash（统计计数）

    Args:
        record: extract_record 返回的结构化字段字典

    Returns:
        是否写入成功
    """
    if not record or not record.get('content_hash'):
        return False

    try:
        _ensure_redis()
        client = redis_util._get_redis_client()
        content_hash = record['content_hash']
        publish_time = record.get('publish_time') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 解析日期和时间戳
        try:
            dt = datetime.strptime(publish_time, '%Y-%m-%d %H:%M:%S')
            date_str = dt.strftime('%Y%m%d')
            timestamp = dt.timestamp()
        except ValueError:
            date_str = datetime.now().strftime('%Y%m%d')
            timestamp = time.time()

        # 构造 Redis Hash 数据
        redis_data = {
            'content_hash': content_hash,
            'source_table': record.get('source_table', ''),
            'title': record.get('title', ''),
            'content': record.get('content', ''),
            'publish_time': publish_time,
            'source': record.get('source', ''),
            'importance_score': str(record.get('importance_score', 0)),
            'business_impact_score': str(record.get('business_impact_score', 0)),
            'composite_score': str(record.get('composite_score', 0)),
            'news_size': record.get('news_size', '小'),
            'news_type': record.get('news_type', '中性'),
            'sectors': record.get('sectors', '[]'),
            'concepts': record.get('concepts', '[]'),
            'leading_stocks': record.get('leading_stocks', '[]'),
            'sector_details': record.get('sector_details', '[]'),
            'analysis_version': record.get('analysis_version', ''),
        }

        pipe = client.pipeline()

        # 1. 新闻详情
        detail_key = f"news:detail:{content_hash}"
        pipe.hmset(detail_key, {k: v.encode('utf-8') if isinstance(v, str) else v for k, v in redis_data.items()})
        pipe.expire(detail_key, DETAIL_TTL)

        # 2. 时间线（按日期）
        timeline_key = f"news:timeline:{date_str}"
        pipe.zadd(timeline_key, {content_hash.encode('utf-8'): timestamp})
        pipe.expire(timeline_key, TIMELINE_TTL)

        # 3. 按类型分组
        type_key = f"news:type:{date_str}:{record.get('news_type', '中性')}"
        pipe.zadd(type_key, {content_hash.encode('utf-8'): timestamp})
        pipe.expire(type_key, TIMELINE_TTL)

        # 4. 评分排行
        top_key = f"news:top:{date_str}"
        pipe.zadd(top_key, {content_hash.encode('utf-8'): float(record.get('composite_score', 0))})
        pipe.expire(top_key, TIMELINE_TTL)

        # 5. 最新列表
        pipe.lpush('news:latest', content_hash.encode('utf-8'))
        pipe.ltrim('news:latest', 0, LATEST_MAX - 1)

        # 6. 统计
        stats_key = f"news:stats:{date_str}"
        pipe.hincrby(stats_key, 'total', 1)
        pipe.hincrby(stats_key, record.get('news_type', '中性'), 1)
        pipe.hincrby(stats_key, f"size_{record.get('news_size', '小')}", 1)
        pipe.expire(stats_key, TIMELINE_TTL)

        # 7. 板块索引
        sectors = record.get('sectors', '[]')
        try:
            sector_list = json.loads(sectors) if isinstance(sectors, str) else sectors
            for sector in sector_list[:10]:  # 最多索引10个板块
                sector_key = f"news:sector:{date_str}:{sector}"
                pipe.sadd(sector_key, content_hash.encode('utf-8'))
                pipe.expire(sector_key, TIMELINE_TTL)
        except (json.JSONDecodeError, TypeError):
            pass

        pipe.execute()
        return True

    except Exception as e:
        logger.warning(f"Redis 写入失败 {record.get('content_hash', '?')}: {e}")
        return False


def process_batch(json_data: str, source_table: str, version: str) -> Dict[str, int]:
    """处理一批 AI 分析结果：拆分 → MySQL → Redis

    Args:
        json_data: AI 返回的完整 JSON 字符串
        source_table: 来源表名
        version: 分析版本

    Returns:
        处理统计 {"total": N, "mysql_ok": N, "redis_ok": N, "failed": N}
    """
    start = time.time()
    stats = {'total': 0, 'mysql_ok': 0, 'redis_ok': 0, 'failed': 0}

    try:
        analysis = json.loads(json_data)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        return stats

    messages = analysis.get('消息集合', [])
    if not messages:
        logger.warning("消息集合为空")
        return stats

    stats['total'] = len(messages)

    for msg in messages:
        try:
            record = extract_record(msg, source_table, version)
            if not record:
                stats['failed'] += 1
                continue

            # 调试：检查关键字段
            if not record.get('title'):
                logger.warning(f"记录缺少 title: hash={record.get('content_hash')}, source_table={source_table}")

            # 写 MySQL
            if save_to_mysql(record):
                stats['mysql_ok'] += 1
            else:
                stats['failed'] += 1
                continue

            # 写 Redis
            if save_to_redis(record):
                stats['redis_ok'] += 1

        except Exception as e:
            stats['failed'] += 1
            logger.error(f"处理消息失败: {e}")

    elapsed = time.time() - start
    logger.info(f"批处理完成: {stats['total']}条, MySQL:{stats['mysql_ok']}, Redis:{stats['redis_ok']}, "
                f"失败:{stats['failed']}, 耗时:{elapsed:.1f}s")

    return stats
