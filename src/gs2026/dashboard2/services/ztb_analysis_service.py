"""涨停分析服务层"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pandas as pd
from sqlalchemy import create_engine

from gs2026.utils import config_util, log_util, redis_util
from gs2026.utils import mysql_util as mu

logger = log_util.setup_logger(__name__)

url = config_util.get_config('common.url')
# 确保使用utf8mb4字符集以支持完整中文
if 'charset=' not in url:
    url += '?charset=utf8mb4'
elif 'charset=utf8&' in url:
    url = url.replace('charset=utf8&', 'charset=utf8mb4&')
elif 'charset=utf8' in url and 'charset=utf8mb4' not in url:
    url = url.replace('charset=utf8', 'charset=utf8mb4')

print(f"[DEBUG] DB URL: {url}")

redis_host = config_util.get_config('common.redis.host', 'localhost')
redis_port = int(config_util.get_config('common.redis.port', 6379))

mysql_tool = mu.MysqlTool(url)
# 使用正确的字符集创建引擎
from sqlalchemy import event
engine = create_engine(
    url, 
    pool_recycle=3600, 
    pool_pre_ping=True
)

# 添加连接事件监听器设置字符集
@event.listens_for(engine, "connect")
def set_utf8mb4(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET NAMES utf8mb4")
    cursor.close()

DETAIL_TTL = 48 * 3600
TIMELINE_TTL = 72 * 3600

# 交易日历缓存
_trading_days_cache = None
_trading_days_cache_time = None


def _get_trading_days():
    """从data_jyrl获取交易日历，带缓存"""
    global _trading_days_cache, _trading_days_cache_time
    
    # 缓存1小时
    if _trading_days_cache is not None and _trading_days_cache_time is not None:
        if datetime.now() - _trading_days_cache_time < timedelta(hours=1):
            logger.debug(f"使用缓存的交易日历，共 {len(_trading_days_cache)} 天")
            return _trading_days_cache
    
    try:
        # 查询交易日：trade_status=1 表示交易日，日期字段是 trade_date
        sql = "SELECT DISTINCT trade_date FROM data_jyrl WHERE trade_status = 1 ORDER BY trade_date"
        df = pd.read_sql(sql, engine)
        _trading_days_cache = set(pd.to_datetime(df['trade_date']).dt.date.tolist())
        _trading_days_cache_time = datetime.now()
        logger.info(f"获取交易日历成功，共 {len(_trading_days_cache)} 天，最近一天: {max(_trading_days_cache) if _trading_days_cache else 'None'}")
        return _trading_days_cache
    except Exception as e:
        logger.warning(f"获取交易日历失败: {e}")
        return set()


def _get_latest_trading_day():
    """获取最近一个交易日（用于默认展示）
    
    逻辑：
    1. 判断当前是否是交易日
    2. 如果是交易日且时间 >= 20:00，返回今天
    3. 否则返回上一个交易日
    """
    trading_days = _get_trading_days()
    now = datetime.now()
    today = now.date()
    
    logger.info(f"_get_latest_trading_day: 当前时间={now}, 今天={today}, 交易日数量={len(trading_days)}")
    
    # 判断今天是否是交易日
    is_trading_day = today in trading_days
    logger.info(f"_get_latest_trading_day: 今天是否是交易日={is_trading_day}, 当前小时={now.hour}")
    
    # 如果是交易日且时间 >= 20:00，返回今天
    if is_trading_day and now.hour >= 20:
        logger.info(f"_get_latest_trading_day: 返回今天 {today}")
        return today
    
    # 否则返回上一个交易日
    sorted_days = sorted([d for d in trading_days if d < today], reverse=True)
    logger.info(f"_get_latest_trading_day: 上一个交易日候选={sorted_days[:5] if sorted_days else 'None'}")
    
    if sorted_days:
        result = sorted_days[0]
        logger.info(f"_get_latest_trading_day: 返回上一个交易日 {result}")
        return result
    
    # 无交易日历数据，回退到昨天
    fallback = today - timedelta(days=1)
    logger.info(f"_get_latest_trading_day: 无交易日历，回退到昨天 {fallback}")
    return fallback


def _ensure_redis():
    client = redis_util._get_redis_client()
    if client is None:
        redis_util.init_redis(host=redis_host, port=int(redis_port), decode_responses=False)


def _decode(val):
    if isinstance(val, bytes):
        return val.decode('utf-8')
    return val


def get_ztb_list(
    date: str = None,
    stock_name: str = None,
    stock_code: str = None,
    sector: str = None,
    concept: str = None,
    zt_time_range: str = None,
    has_expect: int = None,
    continuity: int = None,
    market_filter: str = None,
    cross_date: int = None,  # 新增：跨日期查询标识
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """获取涨停列表
    
    默认查询最近交易日的数据
    当cross_date=1时，跨所有日期查询（用于股票筛选）
    """
    # 根据日期确定表名
    if date and len(date) >= 4:
        table_year = date[:4]
    else:
        table_year = datetime.now().strftime('%Y')
    table_name = f"analysis_ztb_detail_{table_year}"
    
    try:
        where_clauses = []
        
        # 判断是否跨日期查询
        if cross_date:
            # 跨日期模式：不限制日期，查询全年数据
            # 如果传了date，作为可选过滤条件
            if date:
                date_obj = datetime.strptime(date, '%Y%m%d')
                trade_date = date_obj.strftime('%Y-%m-%d')
                where_clauses.append(f"trade_date = '{trade_date}'")
            # 否则查询全年所有日期
        else:
            # 普通模式：必须限制日期
            if not date:
                # 获取最近交易日
                latest_trading_day = _get_latest_trading_day()
                date = latest_trading_day.strftime('%Y%m%d')
            
            date_obj = datetime.strptime(date, '%Y%m%d')
            trade_date = date_obj.strftime('%Y-%m-%d')
            where_clauses.append(f"trade_date = '{trade_date}'")
        
        # 股票筛选条件：同时匹配股票名称和代码
        # 注意：pd.read_sql使用pymysql，%是参数占位符，LIKE中需要转义为%%
        if stock_name:
            where_clauses.append(f"(stock_name LIKE '%%{stock_name}%%' OR stock_code LIKE '%%{stock_name}%%')")
        if stock_code:
            where_clauses.append(f"stock_code = '{stock_code}'")
        if zt_time_range:
            where_clauses.append(f"zt_time_range = '{zt_time_range}'")
        if has_expect is not None:
            where_clauses.append(f"has_expect = {has_expect}")
        if continuity is not None:
            where_clauses.append(f"continuity = {continuity}")
        if sector:
            where_clauses.append(f"JSON_CONTAINS(sectors, '\"{sector}\"')")
        if concept:
            where_clauses.append(f"JSON_CONTAINS(concepts, '\"{concept}\"')")
        
        # 市场板块筛选
        if market_filter and market_filter != 'all':
            if market_filter == 'main':
                where_clauses.append("(stock_code REGEXP '^(600|601|603|605|000|001|002|003)')")
            elif market_filter == 'kcb':
                where_clauses.append("(stock_code REGEXP '^688')")
            elif market_filter == 'cyb':
                where_clauses.append("(stock_code REGEXP '^30')")
            elif market_filter == 'st':
                where_clauses.append("(stock_name REGEXP '^ST' OR stock_name REGEXP '^\\*ST')")
            elif market_filter == 'lhb':
                where_clauses.append("(lhb_analysis IS NOT NULL AND lhb_analysis != '' AND lhb_analysis != '无')")
            elif market_filter == 'no_lhb':
                where_clauses.append("(lhb_analysis IS NULL OR lhb_analysis = '' OR lhb_analysis = '无')")
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        offset = (page - 1) * page_size
        
        # 排序规则：跨日期模式按日期和时间倒序，普通模式按时间升序
        if cross_date:
            order_by = "trade_date DESC, zt_time DESC"
        else:
            order_by = "zt_time ASC"
        
        sql = f"""
            SELECT SQL_CALC_FOUND_ROWS 
                content_hash, stock_name, stock_code, trade_date, zt_time,
                stock_nature, lhb_analysis, sectors, concepts, leading_stocks,
                has_expect, continuity, zt_time_range
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT {page_size} OFFSET {offset}
        """
        
        df = pd.read_sql(sql, engine)
        
        total_sql = "SELECT FOUND_ROWS() as total"
        total_df = pd.read_sql(total_sql, engine)
        total = int(total_df.iloc[0]['total']) if not total_df.empty else 0
        
        items = []
        for _, row in df.iterrows():
            item = row.to_dict()
            # 转换时间字段为字符串
            if item.get('zt_time') is not None:
                try:
                    if hasattr(item['zt_time'], 'total_seconds'):
                        total_seconds = int(item['zt_time'].total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        item['zt_time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        item['zt_time'] = str(item['zt_time'])
                except (ValueError, TypeError):
                    item['zt_time'] = '09:30:00'
            else:
                item['zt_time'] = '09:30:00'
            # 转换日期字段为字符串
            if item.get('trade_date') is not None:
                item['trade_date'] = str(item['trade_date'])
            for key in ('sectors', 'concepts', 'leading_stocks'):
                try:
                    item[key] = json.loads(item.get(key, '[]'))
                except:
                    item[key] = []
            items.append(item)
        
        return {
            'items': items, 
            'total': total, 
            'page': page, 
            'page_size': page_size,
            'query_date': date,
            'cross_date': bool(cross_date)  # 返回跨日期标识
        }
    except Exception as e:
        logger.error(f"涨停列表查询失败: {e}")
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size, 'cross_date': bool(cross_date)}


def get_ztb_detail(content_hash: str, date: str = None) -> Optional[Dict]:
    """获取涨停详情"""
    try:
        # 根据日期确定表名
        if date and len(date) >= 4:
            table_year = date[:4]
        else:
            table_year = datetime.now().strftime('%Y')
        table_name = f"analysis_ztb_detail_{table_year}"
        
        sql = f"SELECT * FROM {table_name} WHERE content_hash = '{content_hash}' LIMIT 1"
        df = pd.read_sql(sql, engine)
        if not df.empty:
            item = df.iloc[0].to_dict()
            # 转换时间字段为字符串
            if item.get('zt_time') is not None:
                try:
                    if hasattr(item['zt_time'], 'total_seconds'):
                        total_seconds = int(item['zt_time'].total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        item['zt_time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        item['zt_time'] = str(item['zt_time'])
                except (ValueError, TypeError):
                    item['zt_time'] = '09:30:00'
            else:
                item['zt_time'] = '09:30:00'
            # 转换日期字段为字符串
            if item.get('trade_date') is not None:
                item['trade_date'] = str(item['trade_date'])
            for key in ('sector_msg', 'concept_msg', 'leading_stock_msg', 
                       'influence_msg', 'expect_msg', 'deep_analysis', 
                       'sectors', 'concepts', 'leading_stocks'):
                try:
                    item[key] = json.loads(item.get(key, '[]'))
                except:
                    item[key] = [] if 'msg' in key or key in ('sectors', 'concepts', 'leading_stocks') else []
            return item
    except Exception as e:
        logger.error(f"涨停详情查询失败: {e}")
    return None


def get_ztb_stats(date: str = None) -> Dict:
    """获取涨停统计
    
    默认查询最近交易日的数据
    """
    if not date:
        # 获取最近交易日
        latest_trading_day = _get_latest_trading_day()
        date = latest_trading_day.strftime('%Y%m%d')
    
    # 根据日期确定表名
    table_year = date[:4] if len(date) >= 4 else datetime.now().strftime('%Y')
    table_name = f"analysis_ztb_detail_{table_year}"
    
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        trade_date = date_obj.strftime('%Y-%m-%d')
        
        sql = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN zt_time_range = 'auction' THEN 1 ELSE 0 END) as auction_count,
                SUM(CASE WHEN zt_time_range = 'early' THEN 1 ELSE 0 END) as early_count,
                SUM(CASE WHEN zt_time_range = 'midday' THEN 1 ELSE 0 END) as midday_count,
                SUM(CASE WHEN zt_time_range = 'closing' THEN 1 ELSE 0 END) as closing_count,
                SUM(CASE WHEN has_expect = 1 THEN 1 ELSE 0 END) as expect_count,
                SUM(CASE WHEN continuity = 1 THEN 1 ELSE 0 END) as continuity_count
            FROM {table_name}
            WHERE trade_date = '{trade_date}'
        """
        
        df = pd.read_sql(sql, engine)
        if not df.empty:
            row = df.iloc[0]
            return {
                'total': int(row['total']),
                'auction_count': int(row['auction_count']),
                'early_count': int(row['early_count']),
                'midday_count': int(row['midday_count']),
                'closing_count': int(row['closing_count']),
                'expect_count': int(row['expect_count']),
                'continuity_count': int(row['continuity_count']),
                'query_date': date
            }
    except Exception as e:
        logger.error(f"涨停统计查询失败: {e}")
    
    return {'total': 0, 'auction_count': 0, 'early_count': 0, 'midday_count': 0, 'closing_count': 0, 
            'expect_count': 0, 'continuity_count': 0, 'query_date': date}


def get_hot_sectors(date: str = None, top: int = 10) -> List[Dict]:
    """获取热门板块
    
    默认查询最近交易日的数据
    """
    if not date:
        # 获取最近交易日
        latest_trading_day = _get_latest_trading_day()
        date = latest_trading_day.strftime('%Y%m%d')
    
    # 根据日期确定表名
    table_year = date[:4] if len(date) >= 4 else datetime.now().strftime('%Y')
    table_name = f"analysis_ztb_detail_{table_year}"
    
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        trade_date = date_obj.strftime('%Y-%m-%d')
        
        sql = f"""
            SELECT 
                JSON_UNQUOTE(JSON_EXTRACT(sectors, '$[0]')) as sector,
                COUNT(*) as count
            FROM {table_name}
            WHERE trade_date = '{trade_date}' AND sectors IS NOT NULL
            GROUP BY JSON_UNQUOTE(JSON_EXTRACT(sectors, '$[0]'))
            HAVING sector IS NOT NULL
            ORDER BY count DESC
            LIMIT {top}
        """
        
        df = pd.read_sql(sql, engine)
        return df.to_dict('records')
    except Exception as e:
        logger.error(f"热门板块查询失败: {e}")
        return []


def get_ztb_timestamps(date: str) -> List[str]:
    """
    获取涨停选股时间轴时间戳列表
    
    与数据监控完全一致:
    1. Redis: monitor_gp_apqd_{date}:timestamps (lrange)
    2. MySQL: SELECT DISTINCT time FROM monitor_gp_apqd_{date}
    
    Args:
        date: 日期，如 "2026-04-29"
    
    Returns:
        时间点列表，如 ["09:30:00", "09:30:03", ...]
    """
    date_str = date.replace('-', '')
    
    # 1. 先查Redis（与数据监控完全一致）
    try:
        client = redis_util._get_redis_client()
        ts_key = f"monitor_gp_apqd_{date_str}:timestamps"
        all_ts = client.lrange(ts_key, 0, -1)
        
        if all_ts:
            # 解码 + 去重 + 排序（与数据监控完全一致）
            timestamps = sorted(set(
                t.decode('utf-8') if isinstance(t, bytes) else t
                for t in all_ts
            ))
            logger.info(f"从Redis获取时间戳: {date}, 共{len(timestamps)}个")
            return timestamps
    except Exception as e:
        logger.warning(f"Redis获取时间戳失败: {e}")
    
    # 2. Redis无，查MySQL（与数据监控完全一致）
    try:
        table_name = f"monitor_gp_apqd_{date_str}"
        sql = f"SELECT DISTINCT time FROM {table_name} ORDER BY time"
        
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        
        if not df.empty:
            timestamps = df['time'].tolist()
            logger.info(f"从MySQL获取时间戳: {date}, 共{len(timestamps)}个")
            return timestamps
    except Exception as e:
        logger.error(f"MySQL获取时间戳失败: {e}")
    
    return []


def get_ztb_list_by_time(date: str, time_str: str) -> Dict:
    """
    获取指定时间点的涨停股票列表
    
    数据查询与数据监控完全一致:
    1. 先查Redis: monitor_gp_sssj_{date}:{time}
    2. Redis无: 查MySQL monitor_gp_sssj_{date} WHERE time={time}
    3. 筛选is_zt=1的股票
    
    Args:
        date: 日期，如 "2026-04-29"
        time_str: 时间，如 "10:00:00"
    
    Returns:
        {
            'zt_stocks': [...],      # 涨停股票列表
            'industries': [...],      # 行业分布
            'concepts': [...],        # 概念分布
            'stats': {...}            # 统计信息
        }
    """
    date_str = date.replace('-', '')
    
    # 1. 先查Redis（与数据监控完全一致）
    df = None
    source = None
    
    try:
        redis_key = f"monitor_gp_sssj_{date_str}:{time_str}"
        df = redis_util.load_dataframe_by_key(redis_key)
        if df is not None and not df.empty:
            source = 'redis'
            logger.info(f"从Redis获取数据: {redis_key}, {len(df)}条")
    except Exception as e:
        logger.warning(f"Redis查询失败: {e}")
    
    # 2. Redis未命中，查MySQL（与数据监控完全一致）
    if df is None or df.empty:
        try:
            table_name = f"monitor_gp_sssj_{date_str}"
            sql = f"SELECT * FROM {table_name} WHERE time = %s"
            df = pd.read_sql(sql, engine, params=(time_str,))
            source = 'mysql'
            logger.info(f"从MySQL获取数据: {table_name}, time={time_str}, {len(df)}条")
        except Exception as e:
            logger.error(f"MySQL查询失败: {e}")
            raise
    
    # 3. 数据为空
    if df is None or df.empty:
        return {
            'zt_stocks': [],
            'industries': [],
            'concepts': [],
            'stats': {
                'total': 0,
                'source': None,
                'time': time_str,
                'date': date
            }
        }
    
    # 4. 筛选is_zt=1的股票
    if 'is_zt' not in df.columns:
        logger.error(f"数据缺少is_zt字段，可用字段: {df.columns.tolist()}")
        raise ValueError("数据缺少is_zt字段")
    
    zt_df = df[df['is_zt'] == 1].copy()
    total_zt = len(zt_df)
    
    logger.info(f"时间点{time_str}涨停股票: {total_zt}/{len(df)}")
    
    # 5. 处理股票列表
    zt_stocks = []
    for _, row in zt_df.iterrows():
        zt_stocks.append({
            'stock_code': str(row.get('stock_code', '')).zfill(6),
            'stock_name': row.get('short_name', ''),
            'price': float(row.get('price', 0)),
            'change_pct': float(row.get('change_pct', 0)),
            'main_net_amount': float(row.get('main_net_amount', 0) or 0),
            'cumulative_main_net': float(row.get('cumulative_main_net', 0) or 0),
            'time': time_str
        })
    
    # 6. 行概分析
    industries = _analyze_industries(zt_stocks)
    concepts = _analyze_concepts(zt_stocks)
    
    return {
        'zt_stocks': zt_stocks,
        'industries': industries,
        'concepts': concepts,
        'stats': {
            'total': total_zt,
            'source': source,
            'time': time_str,
            'date': date,
            'all_stocks': len(df)
        }
    }


def _analyze_industries(stocks: List[Dict]) -> List[Dict]:
    """分析行业分布"""
    if not stocks:
        return []
    
    # 获取行业信息（从stock_bond_mapping_cache）
    try:
        from gs2026.utils.stock_bond_mapping_cache import get_cache
        cache = get_cache()
        
        stock_codes = [s['stock_code'] for s in stocks]
        mappings = cache.get_mappings_batch(stock_codes)
        
        # 统计行业
        industry_stats = {}
        for stock in stocks:
            code = stock['stock_code']
            mapping = mappings.get(code, {})
            industry = mapping.get('industry_name', '未知')
            
            if industry not in industry_stats:
                industry_stats[industry] = {
                    'name': industry,
                    'count': 0,
                    'stocks': []
                }
            
            industry_stats[industry]['count'] += 1
            industry_stats[industry]['stocks'].append({
                'code': code,
                'name': stock['stock_name']
            })
        
        # 排序并返回
        result = sorted(
            industry_stats.values(),
            key=lambda x: x['count'],
            reverse=True
        )
        
        return result
    except Exception as e:
        logger.error(f"行业分析失败: {e}")
        return []


def _analyze_concepts(stocks: List[Dict]) -> List[Dict]:
    """分析概念分布"""
    if not stocks:
        return []
    
    # 获取概念信息（从数据库）
    try:
        stock_codes = [s['stock_code'] for s in stocks]
        
        # 查询概念信息（使用stock_concept_map表）
        codes_str = ','.join([f"'{c}'" for c in stock_codes])
        sql = f"""
            SELECT stock_code, concept_name 
            FROM stock_concept_map 
            WHERE stock_code IN ({codes_str})
        """
        
        try:
            df = pd.read_sql(sql, engine)
        except Exception as e:
            # 如果stock_concept_map表不存在，尝试stock_concept
            if "doesn't exist" in str(e):
                sql = f"""
                    SELECT stock_code, concept_name 
                    FROM stock_concept 
                    WHERE stock_code IN ({codes_str})
                """
                df = pd.read_sql(sql, engine)
            else:
                raise
        
        # 统计概念
        concept_stats = {}
        for _, row in df.iterrows():
            concept = row.get('concept_name', '')
            code = row.get('stock_code', '')
            
            if not concept:
                continue
            
            if concept not in concept_stats:
                concept_stats[concept] = {
                    'name': concept,
                    'count': 0,
                    'stocks': []
                }
            
            # 找到对应的股票名称
            stock_name = next((s['stock_name'] for s in stocks if s['stock_code'] == code), '')
            
            concept_stats[concept]['count'] += 1
            concept_stats[concept]['stocks'].append({
                'code': code,
                'name': stock_name
            })
        
        # 排序并返回前20
        result = sorted(
            concept_stats.values(),
            key=lambda x: x['count'],
            reverse=True
        )
        
        return result[:20]
    except Exception as e:
        logger.error(f"概念分析失败: {e}")
        return []
