"""新闻中心业务逻辑层 —— 从 Redis 优先读取，回源 MySQL。

提供:
    - 新闻列表（分页、按类型/大小/板块筛选）
    - 单条新闻详情
    - 当日统计数据
    - 热点板块排行
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, log_util, mysql_util as mu
from gs2026.utils import redis_util
from pathlib import Path

logger = log_util.setup_logger(str(Path(__file__).absolute()))

url: str = config_util.get_config('common.url')
redis_host: str = config_util.get_config('common.redis.host')
redis_port: int = int(config_util.get_config('common.redis.port'))
mysql_tool = mu.MysqlTool(url)
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)


def _ensure_redis():
    """确保 Redis 已初始化"""
    try:
        redis_util._get_redis_client()
    except RuntimeError:
        redis_util.init_redis(host=redis_host, port=int(redis_port), decode_responses=False)


def _decode(val):
    """bytes → str"""
    if isinstance(val, bytes):
        return val.decode('utf-8')
    return val


def _decode_hash(data: dict) -> dict:
    """解码 Redis Hash 的 bytes 键值"""
    return {_decode(k): _decode(v) for k, v in data.items()}


def get_news_list(
    date: str = None,
    start_time: str = None,
    end_time: str = None,
    news_type: str = None,
    news_size: str = None,
    sector: str = None,
    search: str = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = 'time',
    min_score: int = 0,
) -> Dict[str, Any]:
    """获取新闻列表（优先 Redis，回源 MySQL）

    Args:
        date: 日期 YYYYMMDD，与start_time/end_time互斥
        start_time: 开始时间（格式：YYYY-MM-DD HH:MM:SS）
        end_time: 结束时间（格式：YYYY-MM-DD HH:MM:SS）
        news_type: 利好/利空/中性
        news_size: 重大/大/中/小
        sector: 板块名称
        search: 搜索关键词（全文搜索标题+内容）
        page: 页码（从1开始）
        page_size: 每页条数
        sort_by: 排序方式 time(默认)/score
        min_score: 最低评分阈值（默认0）

    Returns:
        {"items": [...], "total": N, "page": N, "page_size": N, "source": "redis"|"mysql"}
    """
    # 如果有搜索关键词或时间范围，直接走 MySQL（Redis 不支持这些复杂查询）
    if search or (start_time and end_time):
        result = _get_list_from_mysql(date, start_time, end_time, news_type, news_size, sector, page, page_size, sort_by, min_score, search)
        result['source'] = 'mysql'
        return result

    if not date:
        date = datetime.now().strftime('%Y%m%d')

    # 尝试 Redis
    try:
        result = _get_list_from_redis(date, news_type, news_size, sector, page, page_size, sort_by, min_score)
        if result and result.get('items'):
            result['source'] = 'redis'
            return result
    except Exception as e:
        logger.debug(f"Redis 读取失败，回源 MySQL: {e}")

    # 回源 MySQL（使用date模式）
    result = _get_list_from_mysql(date, None, None, news_type, news_size, sector, page, page_size, sort_by, min_score, None)
    result['source'] = 'mysql'
    return result


def _get_list_from_redis(date, news_type, news_size, sector, page, page_size, sort_by, min_score=0):
    """从 Redis 获取新闻列表"""
    _ensure_redis()
    client = redis_util._get_redis_client()

    # 选择 key
    if sector:
        # 板块筛选：先拿 hash 集合再排序
        sector_key = f"news:sector:{date}:{sector}"
        all_hashes = client.smembers(sector_key)
        if not all_hashes:
            return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}
        hashes = [_decode(h) for h in all_hashes]
        total = len(hashes)
        # 分页
        start = (page - 1) * page_size
        hashes = hashes[start:start + page_size]
    elif sort_by == 'score':
        top_key = f"news:top:{date}"
        total = client.zcard(top_key)
        start = (page - 1) * page_size
        hashes = [_decode(h) for h in client.zrevrange(top_key, start, start + page_size - 1)]
    elif news_type:
        type_key = f"news:type:{date}:{news_type}"
        total = client.zcard(type_key)
        start = (page - 1) * page_size
        hashes = [_decode(h) for h in client.zrevrange(type_key, start, start + page_size - 1)]
    else:
        timeline_key = f"news:timeline:{date}"
        total = client.zcard(timeline_key)
        start = (page - 1) * page_size
        hashes = [_decode(h) for h in client.zrevrange(timeline_key, start, start + page_size - 1)]

    if not hashes:
        return {'items': [], 'total': total, 'page': page, 'page_size': page_size}

    # 批量获取详情
    pipe = client.pipeline()
    for h in hashes:
        pipe.hgetall(f"news:detail:{h}")
    results = pipe.execute()

    items = []
    for data in results:
        if data:
            item = _decode_hash(data)
            # 评分过滤
            if min_score > 0:
                try:
                    score = int(item.get('composite_score', 0))
                    if score < min_score:
                        continue
                except (ValueError, TypeError):
                    continue
            # news_size 过滤（Redis 没有专门索引）
            if news_size and item.get('news_size') != news_size:
                continue
            # 解析 JSON 字段
            for key in ('sectors', 'concepts', 'leading_stocks'):
                try:
                    item[key] = json.loads(item.get(key, '[]'))
                except (json.JSONDecodeError, TypeError):
                    item[key] = []
            items.append(item)

    return {'items': items, 'total': total, 'page': page, 'page_size': page_size}


def _get_list_from_mysql(date, start_time, end_time, news_type, news_size, sector, page, page_size, sort_by, min_score=0, search=None):
    """从 MySQL 获取新闻列表"""
    # 时间范围处理
    if start_time and end_time:
        date_start = start_time
        date_end = end_time
    elif date:
        try:
            dt = datetime.strptime(date, '%Y%m%d')
            date_start = dt.strftime('%Y-%m-%d 00:00:00')
            date_end = dt.strftime('%Y-%m-%d 23:59:59')
        except ValueError:
            date_start = datetime.now().strftime('%Y-%m-%d 00:00:00')
            date_end = datetime.now().strftime('%Y-%m-%d 23:59:59')
    else:
        date_start = datetime.now().strftime('%Y-%m-%d 00:00:00')
        date_end = datetime.now().strftime('%Y-%m-%d 23:59:59')

    where = [f"publish_time BETWEEN '{date_start}' AND '{date_end}'"]
    if news_type:
        safe_type = news_type.replace("'", "\\'")
        where.append(f"news_type = '{safe_type}'")
    if news_size:
        safe_size = news_size.replace("'", "\\'")
        where.append(f"news_size = '{safe_size}'")
    if sector:
        safe_sector = sector.replace("'", "\\'")
        where.append(f"JSON_CONTAINS(sectors, '\"{safe_sector}\"')")
    if min_score > 0:
        where.append(f"composite_score >= {min_score}")
    if search:
        safe_search = search.replace("'", " ").replace("\\", " ")
        where.append(f"MATCH(title, content) AGAINST('{safe_search}' IN BOOLEAN MODE)")

    where_str = ' AND '.join(where)
    order = 'composite_score DESC' if sort_by == 'score' else 'publish_time DESC'
    offset = (page - 1) * page_size

    try:
        with engine.connect() as conn:
            # 总数
            count_sql = f"SELECT COUNT(*) as cnt FROM analysis_news_detail_2026 WHERE {where_str}"
            count_df = pd.read_sql(count_sql, conn)
            total = int(count_df.iloc[0]['cnt']) if not count_df.empty else 0

            # 数据
            data_sql = f"""SELECT content_hash, source_table, title, content, publish_time, source,
                                  importance_score, business_impact_score, composite_score,
                                  news_size, news_type, sectors, concepts, leading_stocks, sector_details,
                                  analysis_version, analysis_time
                           FROM analysis_news_detail_2026
                           WHERE {where_str}
                           ORDER BY {order}
                           LIMIT {page_size} OFFSET {offset}"""
            df = pd.read_sql(data_sql, conn)

        items = []
        for _, row in df.iterrows():
            item = row.to_dict()
            # 转换时间字段
            for key in ('publish_time', 'analysis_time'):
                if item.get(key) is not None:
                    item[key] = str(item[key])
            # 解析 JSON 字段
            for key in ('sectors', 'concepts', 'leading_stocks'):
                try:
                    val = item.get(key)
                    item[key] = json.loads(val) if isinstance(val, str) else (val if val else [])
                except (json.JSONDecodeError, TypeError):
                    item[key] = []
            # sector_details
            try:
                val = item.get('sector_details')
                item['sector_details'] = json.loads(val) if isinstance(val, str) else (val if val else [])
            except (json.JSONDecodeError, TypeError):
                item['sector_details'] = []
            # numpy int → python int
            for key in ('importance_score', 'business_impact_score', 'composite_score'):
                item[key] = int(item.get(key, 0))
            items.append(item)

        return {'items': items, 'total': total, 'page': page, 'page_size': page_size}
    except Exception as e:
        logger.error(f"MySQL 查询失败: {e}")
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}


def get_news_detail(content_hash: str) -> Optional[Dict[str, Any]]:
    """获取单条新闻详情

    Args:
        content_hash: 新闻内容 hash

    Returns:
        新闻详情字典，未找到返回 None
    """
    # 优先 Redis
    try:
        _ensure_redis()
        client = redis_util._get_redis_client()
        data = client.hgetall(f"news:detail:{content_hash}")
        if data:
            item = _decode_hash(data)
            for key in ('sectors', 'concepts', 'leading_stocks', 'sector_details'):
                try:
                    item[key] = json.loads(item.get(key, '[]'))
                except (json.JSONDecodeError, TypeError):
                    item[key] = []
            return item
    except Exception:
        pass

    # 回源 MySQL
    try:
        safe_hash = content_hash.replace("'", "\\'").replace("\\", "\\\\")
        sql = f"""SELECT content_hash, source_table, title, content, publish_time, source,
                         importance_score, business_impact_score, composite_score,
                         news_size, news_type, sectors, concepts, leading_stocks, sector_details,
                         analysis_version, analysis_time
                  FROM analysis_news_detail_2026
                  WHERE content_hash = '{safe_hash}'
                  LIMIT 1"""
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        if df.empty:
            return None
        item = df.iloc[0].to_dict()
        for key in ('publish_time', 'analysis_time'):
            if item.get(key) is not None:
                item[key] = str(item[key])
        for key in ('sectors', 'concepts', 'leading_stocks', 'sector_details'):
            try:
                val = item.get(key)
                item[key] = json.loads(val) if isinstance(val, str) else (val if val else [])
            except (json.JSONDecodeError, TypeError):
                item[key] = []
        for key in ('importance_score', 'business_impact_score', 'composite_score'):
            item[key] = int(item.get(key, 0))
        return item
    except Exception as e:
        logger.error(f"MySQL 详情查询失败: {e}")
        return None


def get_news_stats(date: str = None) -> Dict[str, Any]:
    """获取当日新闻统计

    Args:
        date: 日期 YYYYMMDD

    Returns:
        {"total": N, "利好": N, "利空": N, "中性": N, "size_重大": N, ...}
    """
    if not date:
        date = datetime.now().strftime('%Y%m%d')

    # 优先 Redis
    try:
        _ensure_redis()
        client = redis_util._get_redis_client()
        stats_key = f"news:stats:{date}"
        data = client.hgetall(stats_key)
        if data:
            return {_decode(k): int(_decode(v)) for k, v in data.items()}
    except Exception:
        pass

    # 回源 MySQL
    try:
        dt = datetime.strptime(date, '%Y%m%d')
        date_start = dt.strftime('%Y-%m-%d 00:00:00')
        date_end = dt.strftime('%Y-%m-%d 23:59:59')
    except ValueError:
        return {}

    try:
        sql = f"""SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN news_type='利好' THEN 1 ELSE 0 END) as bullish,
                    SUM(CASE WHEN news_type='利空' THEN 1 ELSE 0 END) as bearish,
                    SUM(CASE WHEN news_type='中性' THEN 1 ELSE 0 END) as neutral,
                    SUM(CASE WHEN news_size='重大' THEN 1 ELSE 0 END) as major,
                    SUM(CASE WHEN news_size='大' THEN 1 ELSE 0 END) as big,
                    SUM(CASE WHEN news_size='中' THEN 1 ELSE 0 END) as medium,
                    SUM(CASE WHEN news_size='小' THEN 1 ELSE 0 END) as small_size
                  FROM analysis_news_detail_2026
                  WHERE publish_time BETWEEN '{date_start}' AND '{date_end}'"""
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        if df.empty:
            return {}
        r = df.iloc[0]
        return {
            'total': int(r['total'] or 0), '利好': int(r['bullish'] or 0), '利空': int(r['bearish'] or 0),
            '中性': int(r['neutral'] or 0), 'size_重大': int(r['major'] or 0), 'size_大': int(r['big'] or 0),
            'size_中': int(r['medium'] or 0), 'size_小': int(r['small_size'] or 0),
        }
    except Exception as e:
        logger.error(f"统计查询失败: {e}")
        return {}


def get_hot_sectors(date: str = None, top_n: int = 10) -> List[Dict[str, Any]]:
    """获取热点板块排行

    Args:
        date: 日期 YYYYMMDD
        top_n: 返回前 N 个

    Returns:
        [{"sector": "AI算力", "count": 15, "avg_score": 52.3}, ...]
    """
    if not date:
        date = datetime.now().strftime('%Y%m%d')

    try:
        dt = datetime.strptime(date, '%Y%m%d')
        date_start = dt.strftime('%Y-%m-%d 00:00:00')
        date_end = dt.strftime('%Y-%m-%d 23:59:59')
    except ValueError:
        return []

    sql = f"""SELECT sector_name, COUNT(*) as cnt, ROUND(AVG(composite_score), 1) as avg_score
              FROM (
                  SELECT JSON_UNQUOTE(jt.sector_name) as sector_name, composite_score
                  FROM analysis_news_detail_2026,
                       JSON_TABLE(sectors, '$[*]' COLUMNS (sector_name VARCHAR(100) PATH '$')) AS jt
                  WHERE publish_time BETWEEN '{date_start}' AND '{date_end}'
              ) AS t
              GROUP BY sector_name
              ORDER BY cnt DESC
              LIMIT {top_n}"""

    try:
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        result = []
        for _, row in df.iterrows():
            result.append({
                'sector': str(row['sector_name']) if row['sector_name'] else '',
                'count': int(row['cnt']) if row['cnt'] else 0,
                'avg_score': float(row['avg_score']) if row['avg_score'] else 0.0,
            })
        return result
    except Exception as e:
        logger.error(f"热点板块查询失败: {e}")
        return []
