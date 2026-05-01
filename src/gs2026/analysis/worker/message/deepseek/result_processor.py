"""统一分析结果处理器 —— 支持新闻、领域、涨停、公告分析的拆分入库和Redis缓存。

核心职责:
    1. 将各分析模块的AI返回JSON拆分为单条记录
    2. 结构化字段写入对应的MySQL表
    3. 同步写入Redis缓存
    4. 更新Redis统计信息

支持的分析类型:
    - 新闻分析 (analysis_news_detail_2026)
    - 领域分析 (analysis_domain_detail_2026)
    - 涨停分析 (analysis_ztb_detail_2025)
    - 公告分析 (analysis_notice_detail_2026)

依赖:
    - gs2026.utils: mysql_util, config_util, redis_util, log_util, string_util
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, log_util, mysql_util as mu, string_util
from gs2026.utils import redis_util

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 配置
url: str = config_util.get_config('common.url')
if not url:
    mysql_host = config_util.get_config('mysql.host', '192.168.0.101')
    mysql_port = config_util.get_config('mysql.port', 3306)
    mysql_user = config_util.get_config('mysql.user', 'root')
    mysql_password = config_util.get_config('mysql.password', '123456')
    mysql_database = config_util.get_config('mysql.database', 'gs')
    url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}?charset=utf8"
    logger.warning(f"common.url 未配置，使用手动构建的 URL: {url[:50]}...")

redis_host: str = config_util.get_config('common.redis.host', 'localhost')
redis_port: int = int(config_util.get_config('common.redis.port', 6379))

logger.info(f"ResultProcessor 初始化: url={url[:50]}..., redis={redis_host}:{redis_port}")

mysql_tool = mu.get_mysql_tool(url)
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# Redis 缓存 TTL（秒）
DETAIL_TTL = 48 * 3600      # 单条详情 48 小时
TIMELINE_TTL = 48 * 3600    # 时间线/索引 48 小时


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


def _map_news_type(business_impact_score: int) -> str:
    """根据业务影响评分计算消息类型"""
    if business_impact_score > 0:
        return '利好'
    elif business_impact_score < 0:
        return '利空'
    else:
        return '中性'
LATEST_MAX = 200            # 最新列表最大长度

# 涨停分析专用TTL（1个月 = 30天）
ZTB_DETAIL_TTL = 30 * 24 * 3600   # 30天
ZTB_TIMELINE_TTL = 30 * 24 * 3600  # 30天

# 涨停时间查询缓存（单次分析有效）
_zt_time_cache: Dict[str, str] = {}


def _ensure_redis():
    """确保 Redis 已初始化"""
    client = redis_util._get_redis_client()
    if client is None:
        logger.info("Redis 未初始化，正在初始化...")
        redis_util.init_redis(host=redis_host, port=int(redis_port), decode_responses=False)


def _decode(val):
    """bytes → str"""
    if isinstance(val, bytes):
        return val.decode('utf-8')
    return val


# ============================================================================
# 新闻分析处理
# ============================================================================

def process_news(json_data: str, source_table: str, version: str) -> Dict[str, int]:
    """处理新闻分析结果
    
    Args:
        json_data: AI返回的JSON字符串
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
            record = _extract_news_record(msg, source_table, version)
            if not record:
                stats['failed'] += 1
                continue
            
            # 写MySQL
            if _save_news_to_mysql(record):
                stats['mysql_ok'] += 1
            else:
                stats['failed'] += 1
                continue
            
            # 写Redis
            if _save_news_to_redis(record):
                stats['redis_ok'] += 1
                
        except Exception as e:
            stats['failed'] += 1
            logger.error(f"处理新闻失败: {e}")
    
    elapsed = time.time() - start
    logger.info(f"新闻处理完成: {stats}")
    return stats


def _extract_news_record(msg: Dict, source_table: str, version: str) -> Optional[Dict]:
    """提取新闻记录"""
    content_hash = msg.get('消息id', '')
    if not content_hash:
        logger.warning("消息缺少 content_hash")
        return None
    
    # 从原始新闻表查询冗余字段
    news_info = _get_news_info(content_hash, source_table)
    
    # 计算评分
    importance = int(msg.get('重要程度评分', 0))
    business_impact = int(msg.get('业务影响维度评分', 0))
    composite = importance * 4 + business_impact
    
    # 消息大小映射
    size_map = {'重大': '重大', '大': '大', '中': '中', '小': '小'}
    news_size = size_map.get(msg.get('消息大小', ''), '小')
    
    # 验证消息类型
    news_type = msg.get('消息类型', '中性')
    news_type = str(news_type).strip()
    if news_type not in ['利好', '利空', '中性']:
        news_type = '中性'
    
    return {
        'content_hash': content_hash,
        'source_table': source_table,
        'title': news_info.get('标题', msg.get('标题', '')),
        'content': news_info.get('内容', msg.get('内容', '')),
        'publish_time': news_info.get('发布时间', msg.get('时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))),
        'source': news_info.get('来源', msg.get('来源', '')),
        'importance_score': importance,
        'business_impact_score': business_impact,
        'composite_score': composite,
        'news_size': news_size,
        'news_type': news_type,
        'sectors': json.dumps(msg.get('涉及板块', []), ensure_ascii=False),
        'concepts': json.dumps(msg.get('涉及概念', []), ensure_ascii=False),
        'leading_stocks': json.dumps(msg.get('龙头个股', []), ensure_ascii=False),
        'sector_details': json.dumps(msg.get('板块详情', []), ensure_ascii=False),
        'analysis_version': version,
    }


def _get_news_info(content_hash: str, source_table: str) -> Dict:
    """从原始新闻表查询信息"""
    try:
        query = f"SELECT `标题`, `内容`, `发布时间`, `出处` as `来源` FROM {source_table} WHERE `内容hash` = '{content_hash}' LIMIT 1"
        df = pd.read_sql(query, engine)
        if not df.empty:
            return df.iloc[0].to_dict()
    except Exception as e:
        logger.debug(f"查询新闻信息失败: {e}")
    return {}


def _save_news_to_mysql(record: Dict) -> bool:
    """保存新闻到MySQL"""
    try:
        columns = ', '.join(record.keys())
        def escape_value(v):
            if v is None:
                return 'NULL'
            return "'" + str(v).replace("'", "''") + "'"
        placeholders = ', '.join([escape_value(v) for v in record.values()])
        sql = f"INSERT INTO analysis_news_detail_2026 ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE "
        sql += ', '.join([f"{k}=VALUES({k})" for k in record.keys()])
        mysql_tool.update_data(sql)
        return True
    except Exception as e:
        logger.error(f"MySQL写入失败: {e}")
        return False


def _save_news_to_redis(record: Dict) -> bool:
    """保存新闻到Redis"""
    try:
        _ensure_redis()
        client = redis_util._get_redis_client()
        
        if client is None:
            logger.warning("Redis 不可用，跳过缓存")
            return False
        
        content_hash = record['content_hash']
        date_str = record['publish_time'][:10].replace('-', '')
        
        # 1. 详情Hash
        detail_key = f"news:detail:{content_hash}"
        client.hset(detail_key, mapping={k: str(v) for k, v in record.items()})
        client.expire(detail_key, DETAIL_TTL)
        
        # 2. 时间线ZSet
        timeline_key = f"news:timeline:{date_str}"
        timestamp = int(datetime.strptime(record['publish_time'], '%Y-%m-%d %H:%M:%S').timestamp())
        client.zadd(timeline_key, {content_hash: timestamp})
        client.expire(timeline_key, TIMELINE_TTL)
        
        # 3. 类型索引
        type_key = f"news:type:{date_str}:{record['news_type']}"
        client.zadd(type_key, {content_hash: timestamp})
        client.expire(type_key, TIMELINE_TTL)
        
        # 4. 评分排行
        top_key = f"news:top:{date_str}"
        client.zadd(top_key, {content_hash: record['composite_score']})
        client.expire(top_key, TIMELINE_TTL)
        
        # 5. 板块索引
        sectors = json.loads(record.get('sectors', '[]'))
        for sector in sectors:
            sector_key = f"news:sector:{date_str}:{sector}"
            client.sadd(sector_key, content_hash)
            client.expire(sector_key, TIMELINE_TTL)
        
        # 6. 最新列表
        client.lpush('news:latest', content_hash)
        client.ltrim('news:latest', 0, LATEST_MAX - 1)
        
        return True
    except Exception as e:
        logger.error(f"Redis写入失败: {e}")
        return False


# ============================================================================
# 领域分析处理
# ============================================================================

def process_domain(json_data: str, main_area: str, child_area: str, 
                   event_date: str, version: str = '1.0.0') -> Dict[str, int]:
    """【P2优化】处理领域分析结果：拆分 → MySQL批量插入 → Redis
    
    优化点:
        - MySQL从逐条插入改为批量插入（~30条合并为1次INSERT）
        - 预期性能提升20-30倍
    
    Args:
        json_data: AI返回的JSON字符串
        main_area: 主领域
        child_area: 子领域
        event_date: 事件日期
        version: 分析版本
        
    Returns:
        处理统计
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
    
    # 【P2优化】先提取所有记录
    records = []
    for msg in messages:
        try:
            record = _extract_domain_record(msg, main_area, child_area, version)
            if record:
                records.append(record)
            else:
                stats['failed'] += 1
        except Exception as e:
            stats['failed'] += 1
            logger.error(f"提取领域记录失败: {e}")
    
    if not records:
        logger.warning("无有效领域记录")
        return stats
    
    # 【P2优化】批量插入MySQL（1次INSERT代替~30次）
    mysql_start = time.time()
    key_fields = ['importance_score', 'business_impact_score', 'composite_score',
                  'news_size', 'news_type', 'sectors', 'concepts',
                  'stock_codes', 'reason_analysis', 'deep_analysis', 'analysis_version']
    
    rowcount = mysql_tool.batch_insert_on_duplicate(
        'analysis_domain_detail_2026', records, key_fields)
    
    if rowcount > 0:
        stats['mysql_ok'] = len(records)
        mysql_elapsed = time.time() - mysql_start
        logger.info(f"【P2优化】领域MySQL批量插入完成: {len(records)}条, 耗时:{mysql_elapsed:.2f}s")
    else:
        stats['failed'] += len(records)
        logger.error(f"【P2优化】领域MySQL批量插入失败: {len(records)}条")
        return stats
    
    # Redis保持逐条
    for record in records:
        try:
            if _save_domain_to_redis(record):
                stats['redis_ok'] += 1
        except Exception as e:
            logger.error(f"领域Redis写入失败: {e}")
    
    elapsed = time.time() - start
    logger.info(f"【P2优化】领域处理完成: {stats}, 总耗时:{elapsed:.2f}s")
    return stats


def _extract_domain_record(msg: Dict, main_area: str, child_area: str, version: str) -> Optional[Dict]:
    """提取领域记录"""
    key_event = msg.get('关键事件', '')
    event_time = msg.get('时间', '')
    
    if not key_event or not event_time:
        logger.warning("领域消息缺少关键事件或时间")
        return None
    
    # 生成领域id：关键事件+时间的MD5
    content_hash = string_util.generate_md5(f"{key_event}_{event_time}")
    
    # 计算评分
    importance = int(msg.get('重要程度评分', 0))
    business_impact = int(msg.get('业务影响维度评分', 0))
    composite = importance * 4 + business_impact
    
    # 解析板块/概念/股票代码
    sectors_str = msg.get('涉及板块', '')
    concepts_str = msg.get('涉及概念', '')
    stocks_str = msg.get('股票代码', '')
    
    sectors = [s.strip() for s in sectors_str.split(',') if s.strip()] if sectors_str else []
    concepts = [c.strip() for c in concepts_str.split(',') if c.strip()] if concepts_str else []
    stock_codes = [s.strip() for s in stocks_str.split(',') if s.strip()] if stocks_str else []
    
    # 验证并清洗枚举字段
    # 根据 composite_score 计算消息大小，而不是使用AI返回的值
    news_size = _map_news_size(composite)
    
    # 根据 business_impact_score 计算消息类型，而不是使用AI返回的值
    news_type = _map_news_type(business_impact)
    
    return {
        'content_hash': content_hash,
        'main_area': main_area,
        'child_area': child_area,
        'event_time': event_time,
        'event_source': msg.get('事件来源', ''),
        'key_event': key_event,
        'brief_desc': msg.get('简要描述', ''),
        'importance_score': importance,
        'business_impact_score': business_impact,
        'composite_score': composite,
        'news_size': news_size,
        'news_type': news_type,
        'sectors': json.dumps(sectors, ensure_ascii=False),
        'concepts': json.dumps(concepts, ensure_ascii=False),
        'stock_codes': json.dumps(stock_codes, ensure_ascii=False),
        'reason_analysis': msg.get('原因分析', ''),
        'deep_analysis': json.dumps(msg.get('深度分析', []), ensure_ascii=False),
        'analysis_version': version,
    }


def _save_domain_to_mysql(record: Dict) -> bool:
    """保存领域到MySQL"""
    try:
        columns = ', '.join(record.keys())
        def escape_value(v):
            if v is None:
                return 'NULL'
            return "'" + str(v).replace("'", "''") + "'"
        placeholders = ', '.join([escape_value(v) for v in record.values()])
        sql = f"INSERT INTO analysis_domain_detail_2026 ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE "
        sql += ', '.join([f"{k}=VALUES({k})" for k in record.keys()])
        mysql_tool.update_data(sql)
        return True
    except Exception as e:
        logger.error(f"MySQL写入失败: {e}")
        return False


def _save_domain_to_redis(record: Dict) -> bool:
    """保存领域到Redis"""
    try:
        _ensure_redis()
        client = redis_util._get_redis_client()
        
        if client is None:
            logger.warning("Redis 不可用，跳过缓存")
            return False
        
        content_hash = record['content_hash']
        date_str = record['event_time'][:10].replace('-', '')
        
        # 1. 详情Hash
        detail_key = f"domain:detail:{content_hash}"
        client.hset(detail_key, mapping={k: str(v) for k, v in record.items()})
        client.expire(detail_key, DETAIL_TTL)
        
        # 2. 时间线ZSet
        timeline_key = f"domain:timeline:{date_str}"
        timestamp = int(datetime.strptime(record['event_time'], '%Y-%m-%d %H:%M:%S').timestamp())
        client.zadd(timeline_key, {content_hash: timestamp})
        client.expire(timeline_key, TIMELINE_TTL)
        
        # 3. 领域索引
        area_key = f"domain:area:{record['main_area']}:{record['child_area']}"
        client.sadd(area_key, content_hash)
        
        # 4. 类型索引
        type_key = f"domain:type:{date_str}:{record['news_type']}"
        client.zadd(type_key, {content_hash: timestamp})
        client.expire(type_key, TIMELINE_TTL)
        
        # 5. 板块索引
        sectors = json.loads(record.get('sectors', '[]'))
        for sector in sectors:
            sector_key = f"domain:sector:{date_str}:{sector}"
            client.sadd(sector_key, content_hash)
            client.expire(sector_key, TIMELINE_TTL)
        
        return True
    except Exception as e:
        logger.error(f"Redis写入失败: {e}")
        return False


# ============================================================================
# 涨停分析处理
# ============================================================================

def process_ztb(json_data: str, stock_name: str, trade_date: str,
                stock_code: str = '', version: str = '1.0.0') -> Dict[str, int]:
    """处理涨停分析结果
    
    Args:
        json_data: AI返回的JSON字符串
        stock_name: 股票名称
        trade_date: 交易日期
        stock_code: 股票代码
        version: 分析版本
        
    Returns:
        处理统计
    """
    global _zt_time_cache
    _zt_time_cache = {}  # 每次处理前清空缓存
    
    start = time.time()
    stats = {'total': 0, 'mysql_ok': 0, 'redis_ok': 0, 'failed': 0}
    
    try:
        analysis = json.loads(json_data)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        return stats
    
    stats['total'] = 1  # 涨停分析是单条
    
    try:
        record = _extract_ztb_record(analysis, stock_name, trade_date, stock_code, version)
        if not record:
            stats['failed'] += 1
            return stats
        
        # 写MySQL
        table_year = trade_date[:4] if trade_date and len(trade_date) >= 4 else '2026'
        if _save_ztb_to_mysql(record, table_year):
            stats['mysql_ok'] += 1
        else:
            stats['failed'] += 1
            return stats
        
        # 写Redis
        if _save_ztb_to_redis(record):
            stats['redis_ok'] += 1
            
    except Exception as e:
        stats['failed'] += 1
        logger.error(f"处理涨停失败: {e}")
    
    elapsed = time.time() - start
    logger.info(f"涨停处理完成: {stats}")
    return stats


def _extract_ztb_record(analysis: Dict, stock_name: str, trade_date: str,
                        stock_code: str, version: str) -> Optional[Dict]:
    """提取涨停记录"""
    # 生成content_hash
    content_hash = string_util.generate_md5(stock_name + trade_date)
    
    # 从ztb_day查询真实的首次涨停时间
    real_stock_code = stock_code or analysis.get('股票代码', '')
    zt_time = _get_zt_time_cached(real_stock_code, trade_date)
    if not zt_time:
        # 查询失败则使用AI分析的时间
        zt_time = analysis.get('涨停时间', '09:30:00')
        # 处理带日期的格式
        if ' ' in zt_time:
            zt_time = zt_time.split(' ')[1]
    
    # 涨停时间判断时段
    zt_time_range = _get_zt_time_range(zt_time)
    
    # 提取板块/概念/龙头股
    sectors = []
    for s in analysis.get('板块消息', []):
        if isinstance(s, dict) and '板块' in s:
            sectors.append(s['板块'])
    
    concepts = []
    for c in analysis.get('概念消息', []):
        if isinstance(c, dict) and '概念' in c:
            concepts.append(c['概念'])
    
    leading_stocks = []
    for l in analysis.get('龙头股消息', []):
        if isinstance(l, dict) and '龙头股' in l:
            leading_stocks.append(l['龙头股'])
    
    # 预期消息判断
    expect_msgs = analysis.get('预期涨停消息', [])
    has_expect = 1 if expect_msgs else 0
    continuity = 1 if any(e.get('延续性') == '是' for e in expect_msgs) else 0
    
    return {
        'content_hash': content_hash,
        'stock_name': stock_name,
        'stock_code': stock_code or analysis.get('股票代码', ''),
        'trade_date': trade_date,
        'zt_time': zt_time,
        'zt_time_range': zt_time_range,
        'stock_nature': analysis.get('股性分析', ''),
        'lhb_analysis': analysis.get('龙虎榜分析', ''),
        'sector_msg': json.dumps(analysis.get('板块消息', []), ensure_ascii=False),
        'concept_msg': json.dumps(analysis.get('概念消息', []), ensure_ascii=False),
        'leading_stock_msg': json.dumps(analysis.get('龙头股消息', []), ensure_ascii=False),
        'influence_msg': json.dumps(analysis.get('消息', []), ensure_ascii=False),
        'expect_msg': json.dumps(expect_msgs, ensure_ascii=False),
        'deep_analysis': json.dumps(analysis.get('深度分析', []), ensure_ascii=False),
        'sectors': json.dumps(sectors, ensure_ascii=False),
        'concepts': json.dumps(concepts, ensure_ascii=False),
        'leading_stocks': json.dumps(leading_stocks, ensure_ascii=False),
        'has_expect': has_expect,
        'continuity': continuity,
        'analysis_version': version,
    }


def _get_zt_time_range(zt_time: str) -> str:
    """根据涨停时间判断时段
    
    时段划分（基于真实的zt_time）：
    - auction: 竞价 (09:15:00-09:30:00，包含9:30:00)
    - early: 早盘 (09:30:00-11:30:00，包含11:30:00)
    - midday: 午盘 (13:00:00-14:57:00，包含14:57:00)
    - closing: 尾盘竞价 (14:57:00-15:00:00，包含15:00:00)
    """
    try:
        # 处理时间格式，提取HH:MM:SS
        if ' ' in zt_time:
            zt_time = zt_time.split(' ')[1]
        
        parts = zt_time.split(':')
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        
        # 转换为总秒数便于比较
        total_seconds = hour * 3600 + minute * 60 + second
        
        # 09:15:00 = 33300, 09:30:00 = 34200
        # 11:30:00 = 41400
        # 13:00:00 = 46800, 14:57:00 = 53820
        # 15:00:00 = 54000
        if total_seconds <= 34200:  # 09:15:00 - 09:30:00 竞价（含9:30:00）
            return 'auction'
        elif total_seconds <= 41400:  # 09:30:00 - 11:30:00 早盘（含11:30:00）
            return 'early'
        elif total_seconds <= 46800:  # 11:30:00 - 13:00:00 午休，归为早盘
            return 'early'
        elif total_seconds <= 53820:  # 13:00:00 - 14:57:00 午盘（含14:57:00）
            return 'midday'
        else:  # 14:57:00 - 15:00:00 尾盘竞价（含15:00:00）
            return 'closing'
    except Exception as e:
        logger.warning(f"时段计算失败: {zt_time}, 错误: {e}")
        return 'early'


# ============================================================================
# 涨停时间查询（从ztb_day获取真实时间）
# ============================================================================

def _get_zt_time_from_db(stock_code: str, trade_date: str) -> Optional[str]:
    """从ztb_day查询首次涨停时间"""
    try:
        sql = f"""
            SELECT 首次涨停时间 
            FROM ztb_day 
            WHERE 股票代码 = '{stock_code}' 
            AND trade_date = '{trade_date}'
            LIMIT 1
        """
        df = pd.read_sql(sql, engine)
        if not df.empty:
            # 处理时间格式，可能是Timedelta或字符串
            zt_time = df.iloc[0]['首次涨停时间']
            if hasattr(zt_time, 'total_seconds'):
                # Timedelta类型
                total_seconds = int(zt_time.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                # 字符串类型，处理 HH:MM:SS 格式
                zt_time_str = str(zt_time)
                if ' ' in zt_time_str:
                    zt_time_str = zt_time_str.split(' ')[1]
                return zt_time_str
    except Exception as e:
        logger.warning(f"查询ztb_day失败: {e}")
    return None


def _get_zt_time_cached(stock_code: str, trade_date: str) -> Optional[str]:
    """带缓存的涨停时间查询"""
    global _zt_time_cache
    cache_key = f"{stock_code}_{trade_date}"
    if cache_key in _zt_time_cache:
        return _zt_time_cache[cache_key]
    
    zt_time = _get_zt_time_from_db(stock_code, trade_date)
    if zt_time:
        _zt_time_cache[cache_key] = zt_time
    return zt_time


def _save_ztb_to_mysql(record: Dict, table_year: str = None) -> bool:
    """保存涨停到MySQL"""
    try:
        # 根据交易日期确定表名
        if table_year is None:
            trade_date = record.get('trade_date', '')
            if trade_date and len(trade_date) >= 4:
                table_year = trade_date[:4]
            else:
                table_year = '2026'  # 默认年份
        
        table_name = f"analysis_ztb_detail_{table_year}"
        columns = ', '.join(record.keys())
        def escape_value(v):
            if v is None:
                return 'NULL'
            return "'" + str(v).replace("'", "''") + "'"
        placeholders = ', '.join([escape_value(v) for v in record.values()])
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE "
        sql += ', '.join([f"{k}=VALUES({k})" for k in record.keys()])
        mysql_tool.update_data(sql)
        return True
    except Exception as e:
        logger.error(f"MySQL写入失败: {e}")
        return False


def _save_ztb_to_redis(record: Dict) -> bool:
    """保存涨停到Redis"""
    try:
        _ensure_redis()
        client = redis_util._get_redis_client()
        
        if client is None:
            logger.warning("Redis 不可用，跳过缓存")
            return False
        
        content_hash = record['content_hash']
        # 处理日期格式，可能是 '2026-04-13' 或 '2026-04-13 09:30:00'
        trade_date = record['trade_date']
        date_str = trade_date[:10].replace('-', '')
        
        # 1. 详情Hash - 使用涨停专用TTL（30天）
        detail_key = f"ztb:detail:{content_hash}"
        client.hset(detail_key, mapping={k: str(v) for k, v in record.items()})
        client.expire(detail_key, ZTB_DETAIL_TTL)
        
        # 2. 时间线ZSet（按涨停时间排序）- 使用涨停专用TTL（30天）
        timeline_key = f"ztb:timeline:{date_str}"
        zt_time = record.get('zt_time', '00:00:00')
        # 处理涨停时间格式，可能是 '09:30:00' 或 '2026-04-13 09:30:00'
        if ' ' in zt_time:
            zt_time = zt_time.split(' ')[1]  # 提取时间部分
        time_parts = zt_time.split(':')
        score = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
        client.zadd(timeline_key, {content_hash: score})
        client.expire(timeline_key, ZTB_TIMELINE_TTL)
        
        # 3. 时段索引 - 使用涨停专用TTL（30天）
        time_range = record.get('zt_time_range', 'mid')
        range_key = f"ztb:timeline:{date_str}:{time_range}"
        client.zadd(range_key, {content_hash: score})
        client.expire(range_key, ZTB_TIMELINE_TTL)
        
        # 4. 板块索引 - 使用涨停专用TTL（30天）
        sectors = json.loads(record.get('sectors', '[]'))
        for sector in sectors:
            sector_key = f"ztb:sector:{date_str}:{sector}"
            client.sadd(sector_key, content_hash)
            client.expire(sector_key, ZTB_TIMELINE_TTL)
        
        # 5. 特殊标记 - 使用涨停专用TTL（30天）
        if record.get('has_expect'):
            expect_key = f"ztb:expect:{date_str}"
            client.sadd(expect_key, content_hash)
            client.expire(expect_key, ZTB_TIMELINE_TTL)
        
        if record.get('continuity'):
            continuity_key = f"ztb:continuity:{date_str}"
            client.sadd(continuity_key, content_hash)
            client.expire(continuity_key, ZTB_TIMELINE_TTL)
        
        return True
    except Exception as e:
        logger.error(f"Redis写入失败: {e}")
        return False


# ============================================================================
# 公告分析处理
# ============================================================================

def process_notice(json_data: str, version: str = '1.0.0') -> Dict[str, int]:
    """【P2优化】处理公告分析结果：拆分 → MySQL批量插入 → Redis
    
    优化点:
        - MySQL从逐条插入改为批量插入（5-15条合并为1次INSERT）
        - 预期性能提升5-15倍
    
    Args:
        json_data: AI返回的JSON字符串
        version: 分析版本
        
    Returns:
        处理统计
    """
    start = time.time()
    stats = {'total': 0, 'mysql_ok': 0, 'redis_ok': 0, 'failed': 0}
    
    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        return stats
    
    notices = data.get('公告集合', [])
    if not notices:
        logger.warning("公告集合为空")
        return stats
    
    stats['total'] = len(notices)
    
    # 【P2优化】先提取所有记录
    records = []
    for notice in notices:
        try:
            record = _extract_notice_record(notice, version)
            if record:
                records.append(record)
            else:
                stats['failed'] += 1
        except Exception as e:
            stats['failed'] += 1
            logger.error(f"提取公告记录失败: {e}")
    
    if not records:
        logger.warning("无有效公告记录")
        return stats
    
    # 【P2优化】批量插入MySQL（1次INSERT代替5-15次）
    mysql_start = time.time()
    key_fields = ['risk_level', 'notice_type', 'notice_category',
                  'market_expectation', 'open_prediction', 'duration', 'overnight_strategy',
                  'judgment_basis', 'key_points', 'short_term_impact', 'medium_term_impact',
                  'risk_score', 'type_score', 'analysis_version']
    
    rowcount = mysql_tool.batch_insert_on_duplicate(
        'analysis_notice_detail_2026', records, key_fields)
    
    if rowcount > 0:
        stats['mysql_ok'] = len(records)
        mysql_elapsed = time.time() - mysql_start
        logger.info(f"【P2优化】公告MySQL批量插入完成: {len(records)}条, 耗时:{mysql_elapsed:.2f}s")
    else:
        stats['failed'] += len(records)
        logger.error(f"【P2优化】公告MySQL批量插入失败: {len(records)}条")
        return stats
    
    # Redis保持逐条
    for record in records:
        try:
            if _save_notice_to_redis(record):
                stats['redis_ok'] += 1
        except Exception as e:
            logger.error(f"公告Redis写入失败: {e}")
    
    elapsed = time.time() - start
    logger.info(f"【P2优化】公告处理完成: {stats}, 总耗时:{elapsed:.2f}s")
    return stats


def _extract_notice_record(notice: Dict, version: str) -> Optional[Dict]:
    """提取公告记录"""
    notice_id = notice.get('公告id', '')
    if not notice_id:
        logger.warning("公告缺少ID")
        return None
    
    content_hash = string_util.generate_md5(notice_id)
    
    # 风险等级转评分（Prompt中为"影响力度"，映射到risk_level）
    risk_map = {'高': 75, '中': 50, '低': 25}
    risk_level = notice.get('影响力度', notice.get('风险大小', '中'))
    # 清洗数据：去除空格，验证枚举值
    risk_level = str(risk_level).strip()
    if risk_level not in ['高', '中', '低']:
        risk_level = '中'  # 默认值
    risk_score = risk_map.get(risk_level, 50)
    
    # 消息类型转评分
    type_map = {'利好': 75, '中性': 50, '利空': 25}
    notice_type = notice.get('消息类型', '中性')
    # 清洗数据：去除空格，验证枚举值
    notice_type = str(notice_type).strip()
    if notice_type not in ['利好', '利空', '中性']:
        notice_type = '中性'  # 默认值
    type_score = type_map.get(notice_type, 50)
    
    # 处理判定依据（可能是列表或字符串）
    judgment_basis = notice.get('判定依据', [])
    if isinstance(judgment_basis, list):
        judgment_basis = json.dumps(judgment_basis, ensure_ascii=False)
    else:
        judgment_basis = str(judgment_basis) if judgment_basis else ''
    
    # 处理关键要点（可能是列表或字符串）
    key_points = notice.get('关键要点', [])
    if isinstance(key_points, list):
        key_points = json.dumps(key_points, ensure_ascii=False)
    else:
        key_points = str(key_points) if key_points else ''
    
    return {
        'content_hash': content_hash,
        'notice_id': notice_id,
        'stock_code': notice.get('股票代码', ''),
        'stock_name': notice.get('股票名称', ''),
        'notice_date': notice.get('公告日期', datetime.now().strftime('%Y-%m-%d')),
        'notice_title': notice.get('公告标题', ''),
        'notice_content': '',  # AI不返回内容，保持为空
        'risk_level': risk_level,
        'notice_type': notice_type,
        'notice_category': str(notice.get('公告类型', '')).strip()[:64],  # 【新增】公告类型分类
        'market_expectation': str(notice.get('市场预期', '')).strip()[:16],  # 【新增】市场预期
        'open_prediction': str(notice.get('开盘预判', '')).strip()[:32],  # 【新增】开盘预判
        'duration': str(notice.get('持续性', '')).strip()[:16],  # 【新增】持续性
        'overnight_strategy': str(notice.get('隔夜策略', '')).strip()[:500],  # 【新增】隔夜策略
        'judgment_basis': judgment_basis,
        'key_points': key_points,
        'short_term_impact': notice.get('短线影响', ''),
        'medium_term_impact': notice.get('中线影响', ''),
        'risk_score': risk_score,
        'type_score': type_score,
        'analysis_version': version,
    }


def _save_notice_to_mysql(record: Dict) -> bool:
    """保存公告到MySQL"""
    try:
        columns = ', '.join(record.keys())
        def escape_value(v):
            if v is None:
                return 'NULL'
            return "'" + str(v).replace("'", "''") + "'"
        placeholders = ', '.join([escape_value(v) for v in record.values()])
        sql = f"INSERT INTO analysis_notice_detail_2026 ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE "
        sql += ', '.join([f"{k}=VALUES({k})" for k in record.keys()])
        mysql_tool.update_data(sql)
        return True
    except Exception as e:
        logger.error(f"MySQL写入失败: {e}")
        return False


def _save_notice_to_redis(record: Dict) -> bool:
    """保存公告到Redis"""
    try:
        _ensure_redis()
        client = redis_util._get_redis_client()
        
        if client is None:
            logger.warning("Redis 不可用，跳过缓存")
            return False
        
        content_hash = record['content_hash']
        # 处理日期格式，可能是 '2026-04-13' 或 '2026-04-13 09:30:00'
        notice_date = record['notice_date']
        date_str = notice_date[:10].replace('-', '')
        
        # 1. 详情Hash
        detail_key = f"notice:detail:{content_hash}"
        client.hset(detail_key, mapping={k: str(v) for k, v in record.items()})
        client.expire(detail_key, DETAIL_TTL)
        
        # 2. 时间线ZSet
        timeline_key = f"notice:timeline:{date_str}"
        # 使用notice_id作为score保证顺序
        client.zadd(timeline_key, {content_hash: int(time.time())})
        client.expire(timeline_key, TIMELINE_TTL)
        
        # 3. 类型索引
        type_key = f"notice:type:{date_str}:{record['notice_type']}"
        client.zadd(type_key, {content_hash: int(time.time())})
        client.expire(type_key, TIMELINE_TTL)
        
        # 4. 风险等级索引
        risk_key = f"notice:risk:{date_str}:{record['risk_level']}"
        client.sadd(risk_key, content_hash)
        client.expire(risk_key, TIMELINE_TTL)
        
        # 5. 股票索引
        stock_key = f"notice:stock:{record['stock_code']}"
        client.sadd(stock_key, content_hash)
        
        return True
    except Exception as e:
        logger.error(f"Redis写入失败: {e}")
        return False
