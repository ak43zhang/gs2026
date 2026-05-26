"""智谱清言分析结果处理器 —— 支持领域分析的拆分入库和Redis缓存。

核心职责:
    1. 将智谱清言AI返回JSON拆分为单条记录
    2. 结构化字段写入对应的MySQL表
    3. 同步写入Redis缓存
    4. 更新Redis统计信息

支持的分析类型:
    - 领域分析 (analysis_domain_detail_chatglm_2026)

依赖:
    - gs2026.utils: mysql_util, config_util, redis_util, log_util, string_util
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine

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


# ============================================================================
# 领域分析处理
# ============================================================================

def process_domain(json_data: str, main_area: str, child_area: str, 
                   event_date: str, version: str = 'zhipuqingyan-1.0.0') -> Dict[str, int]:
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
    
    # 根据 composite_score 计算消息大小
    news_size = _map_news_size(composite)
    
    # 根据 business_impact_score 计算消息类型
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
