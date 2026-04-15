"""新闻中心业务逻辑层 —— 从 Redis 优先读取，回源 MySQL。

提供:
    - 新闻列表（分页、按类型/大小/板块筛选）
    - 单条新闻详情
    - 当日统计数据
    - 热点板块排行
"""

import json
import time
from datetime import datetime, time, timedelta
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

# 交易日历缓存
_trading_days_cache: set = None
_trading_days_cache_time: datetime = None


def _get_trading_days() -> set:
    """从data_jyrl获取交易日历"""
    try:
        # 查询交易日：trade_status=1 表示交易日，日期字段是 trade_date
        sql = "SELECT DISTINCT trade_date FROM data_jyrl WHERE trade_status = 1 ORDER BY trade_date"
        df = pd.read_sql(sql, engine)
        trading_days = set(pd.to_datetime(df['trade_date']).dt.date.tolist())
        logger.info(f"_get_trading_days: 获取到 {len(trading_days)} 个交易日，最近5个={sorted([d for d in trading_days if d <= datetime.now().date()], reverse=True)[:5]}")
        return trading_days
    except Exception as e:
        logger.warning(f"获取交易日历失败: {e}")
        return set()


def _get_previous_trading_day(date: datetime.date, trading_days: set) -> datetime.date:
    """获取指定日期的上一个交易日"""
    sorted_days = sorted([d for d in trading_days if d < date], reverse=True)
    logger.info(f"_get_previous_trading_day: 查找 {date} 之前的交易日，候选数量={len(sorted_days)}, 最近5个={sorted_days[:5]}")
    if sorted_days:
        return sorted_days[0]
    # 无交易日历数据，回退到自然日
    return date - timedelta(days=1)


def get_news_time_range(target_date: str = None, target_time: datetime = None) -> Dict[str, Any]:
    """
    计算新闻分析的时间范围
    
    当前时间模式（target_date=None）：
        - 范围：上一个交易日 15:00 → 当前时间
        - 如果时间范围 < 6小时：扩展到上上个交易日 15:00 → 当前时间
    
    日期选择模式（target_date=YYYYMMDD）：
        - 范围：所选日期的上一个交易日 15:00 → 所选日期 23:59:59
    
    Args:
        target_date: 选择的日期（YYYYMMDD格式），None表示当前时间模式
        target_time: 当前时间（仅当前时间模式使用）
    
    Returns:
        {
            'start_time': datetime,      # 范围开始
            'end_time': datetime,        # 范围结束
            'display_date': str,         # 显示日期（YYYY-MM-DD）
            'trading_day': str,          # 参考交易日（YYYY-MM-DD）
            'is_extended': bool,         # 是否已扩展
            'hours_span': float          # 时间跨度（小时）
        }
    """
    trading_days = _get_trading_days()
    
    if target_date is None:
        # 当前时间模式
        now = target_time or datetime.now()
        today = now.date()
        
        # 获取上个交易日
        prev_trading_day = _get_previous_trading_day(today, trading_days)
        start_time = datetime.combine(prev_trading_day, time(15, 0, 0))
        end_time = now
        
        # 检查是否需要扩展
        hours_span = (end_time - start_time).total_seconds() / 3600
        is_extended = False
        
        logger.info(f"get_news_time_range: 今天={today}, 上个交易日={prev_trading_day}, 初始时间范围={start_time} ~ {end_time}, 跨度={hours_span:.1f}小时")
        
        if hours_span < 6:
            # 扩展到上上个交易日
            prev_prev_trading_day = _get_previous_trading_day(prev_trading_day, trading_days)
            start_time = datetime.combine(prev_prev_trading_day, time(15, 0, 0))
            hours_span = (end_time - start_time).total_seconds() / 3600
            is_extended = True
            trading_day = prev_prev_trading_day
            display_date = prev_prev_trading_day.strftime('%Y-%m-%d')  # 显示实际起始日期
            logger.info(f"get_news_time_range: 时间范围<6小时，扩展到上上个交易日={prev_prev_trading_day}, 新时间范围={start_time} ~ {end_time}, 跨度={hours_span:.1f}小时")
        else:
            trading_day = prev_trading_day
            display_date = prev_trading_day.strftime('%Y-%m-%d')
        
    else:
        # 日期选择器模式
        try:
            selected_date = datetime.strptime(target_date, '%Y%m%d').date()
        except ValueError:
            selected_date = datetime.now().date()
        
        prev_trading_day = _get_previous_trading_day(selected_date, trading_days)
        
        start_time = datetime.combine(prev_trading_day, time(15, 0, 0))
        end_time = datetime.combine(selected_date, time(23, 59, 59))
        
        hours_span = (end_time - start_time).total_seconds() / 3600
        is_extended = False
        trading_day = selected_date
        display_date = selected_date.strftime('%Y-%m-%d')
    
    return {
        'start_time': start_time,
        'end_time': end_time,
        'display_date': display_date,
        'trading_day': trading_day.strftime('%Y-%m-%d'),
        'is_extended': is_extended,
        'hours_span': round(hours_span, 1)
    }


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
        date: 日期 YYYYMMDD，None表示当前时间模式
        start_time: 开始时间（格式：YYYY-MM-DD HH:MM:SS），与date互斥
        end_time: 结束时间（格式：YYYY-MM-DD HH:MM:SS），与date互斥
        news_type: 利好/利空/中性
        news_size: 重大/大/中/小
        sector: 板块名称
        search: 搜索关键词（全文搜索标题+内容）
        page: 页码（从1开始）
        page_size: 每页条数
        sort_by: 排序方式 time(默认)/score
        min_score: 最低评分阈值（默认0）

    Returns:
        {
            "items": [...], 
            "total": N, 
            "page": N, 
            "page_size": N, 
            "source": "redis"|"mysql",
            "time_range": {...}  # 新增：时间范围信息
        }
    """
    # 计算时间范围
    time_range_info = get_news_time_range(date)
    start_dt = time_range_info['start_time']
    end_dt = time_range_info['end_time']
    
    # 如果有自定义时间范围，使用自定义的
    if start_time and end_time:
        start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        end_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
    
    start_time_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_time_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # 直接走MySQL（时间范围查询不支持Redis）
    result = _get_list_from_mysql_by_time_range(
        start_time_str, end_time_str, news_type, news_size, sector, 
        page, page_size, sort_by, min_score, search
    )
    result['source'] = 'mysql'
    result['time_range'] = {
        'start': start_time_str,
        'end': end_time_str,
        'display_date': time_range_info['display_date'],
        'is_extended': time_range_info['is_extended'],
        'hours_span': time_range_info['hours_span']
    }
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


def _get_list_from_mysql_by_time_range(
    start_time: str, end_time: str, news_type: str = None, 
    news_size: str = None, sector: str = None, page: int = 1, 
    page_size: int = 20, sort_by: str = 'time', min_score: int = 0, 
    search: str = None
) -> Dict[str, Any]:
    """从 MySQL 按时间范围获取新闻列表"""
    
    where = [f"publish_time BETWEEN '{start_time}' AND '{end_time}'"]
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
        logger.error(f"MySQL 时间范围查询失败: {e}")
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}


def get_news_stats(date: str = None) -> Dict[str, Any]:
    """获取当日新闻统计（按交易日时间范围）

    Args:
        date: 日期 YYYYMMDD，None表示当前时间模式

    Returns:
        {
            "total": N, "利好": N, "利空": N, "中性": N, "size_重大": N,
            "time_range": {...}
        }
    """
    # 计算时间范围
    time_range_info = get_news_time_range(date)
    start_time = time_range_info['start_time'].strftime('%Y-%m-%d %H:%M:%S')
    end_time = time_range_info['end_time'].strftime('%Y-%m-%d %H:%M:%S')

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
                  WHERE publish_time BETWEEN '{start_time}' AND '{end_time}'"""
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        if df.empty:
            return {'time_range': time_range_info}
        r = df.iloc[0]
        return {
            'total': int(r['total'] or 0), '利好': int(r['bullish'] or 0), '利空': int(r['bearish'] or 0),
            '中性': int(r['neutral'] or 0), 'size_重大': int(r['major'] or 0), 'size_大': int(r['big'] or 0),
            'size_中': int(r['medium'] or 0), 'size_小': int(r['small_size'] or 0),
            'time_range': time_range_info
        }
    except Exception as e:
        logger.error(f"统计查询失败: {e}")
        return {'time_range': time_range_info}


def get_hot_sectors(date: str = None, top_n: int = 10) -> List[Dict[str, Any]]:
    """获取热点板块排行（按交易日时间范围）

    Args:
        date: 日期 YYYYMMDD，None表示当前时间模式
        top_n: 返回前 N 个

    Returns:
        [{"sector": "AI算力", "count": 15, "avg_score": 52.3}, ...]
    """
    # 计算时间范围
    time_range_info = get_news_time_range(date)
    start_time = time_range_info['start_time'].strftime('%Y-%m-%d %H:%M:%S')
    end_time = time_range_info['end_time'].strftime('%Y-%m-%d %H:%M:%S')

    sql = f"""SELECT sector_name, COUNT(*) as cnt, ROUND(AVG(composite_score), 1) as avg_score
              FROM (
                  SELECT JSON_UNQUOTE(jt.sector_name) as sector_name, composite_score
                  FROM analysis_news_detail_2026,
                       JSON_TABLE(sectors, '$[*]' COLUMNS (sector_name VARCHAR(100) PATH '$')) AS jt
                  WHERE publish_time BETWEEN '{start_time}' AND '{end_time}'
                    AND news_type = '利好'
                    AND news_size = '重大'
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
