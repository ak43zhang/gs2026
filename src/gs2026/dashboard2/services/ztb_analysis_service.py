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
    """获取指定日期的时间戳列表
    
    Args:
        date: 日期字符串 (YYYY-MM-DD)
        
    Returns:
        时间戳列表 (HH:MM:SS格式)
    """
    try:
        # 从Redis获取时间戳列表
        date_str = date.replace('-', '')
        redis_key = f"monitor_gp_apqd_{date_str}:timestamps"
        
        try:
            from gs2026.utils.redis_util import _get_redis_client
            redis_client = _get_redis_client()
            
            if redis_client:
                # 获取所有时间戳（从列表中读取）
                timestamps = redis_client.lrange(redis_key, 0, -1)
                if timestamps:
                    # 解码并排序（从早到晚）
                    timestamps = [ts.decode('utf-8') if isinstance(ts, bytes) else ts for ts in timestamps]
                    timestamps.reverse()  # Redis lpush是先入后出，需要反转
                    logger.info(f"从Redis获取时间戳: {date}, 共{len(timestamps)}个")
                    return timestamps
                else:
                    logger.warning(f"Redis中没有时间戳数据: {redis_key}")
            else:
                logger.warning("Redis客户端未初始化")
        except Exception as e:
            logger.warning(f"Redis查询失败: {e}")
        
        # 2. 从MySQL获取（回退）
        try:
            table_name = f"monitor_gp_sssj_{date_str}"
            sql = f"""
                SELECT DISTINCT time FROM {table_name}
                ORDER BY time
            """
            df = pd.read_sql(sql, engine)
            if not df.empty:
                timestamps = df['time'].tolist()
                logger.info(f"从MySQL获取时间戳: {date}, 共{len(timestamps)}个")
                return timestamps
            else:
                logger.warning(f"MySQL中没有时间戳数据: {table_name}")
        except Exception as e:
            logger.warning(f"MySQL查询失败: {e}")
        
        return []
    except Exception as e:
        logger.error(f"获取时间戳失败: {e}")
        return []


def get_ztb_snapshot(date: str, time: str) -> Dict:
    """获取指定时间点的涨停快照（复用原有涨停标签分析逻辑）
    
    Args:
        date: 日期字符串 (YYYY-MM-DD)
        time: 时间字符串 (HH:MM:SS)
        
    Returns:
        涨停快照数据 {
            'total_count': 涨停总数,
            'industries': [{'code': '881121', 'name': '半导体', 'count': 15}, ...],
            'concepts': [{'code': '886055', 'name': '芯片', 'count': 10}, ...]
        }
    """
    try:
        date_str = date.replace('-', '')
        
        # 1. 获取指定时间点的涨停股票数据
        df = _get_zt_stocks_at_time(date_str, time)
        
        if df.empty:
            logger.warning(f"该时间点无涨停股票: {date} {time}")
            return {'total_count': 0, 'industries': [], 'concepts': []}
        
        # 提取股票代码列表
        zt_codes = df['stock_code'].astype(str).tolist()
        logger.info(f"获取涨停股票: {date} {time}, 共{len(zt_codes)}只")
        
        # 2. 【复用】使用原有逻辑分析行业和概念分布
        result = _analyze_ztb_tags(zt_codes)
        
        return {
            'total_count': len(zt_codes),
            'industries': result['industries'],
            'concepts': result['concepts']
        }
    except Exception as e:
        logger.error(f"获取涨停快照失败: {e}")
        return {'total_count': 0, 'industries': [], 'concepts': []}


def _get_zt_stocks_at_time(date_str: str, time: str) -> pd.DataFrame:
    """获取指定时间点正在涨停的股票数据（is_zt=1）
    
    Args:
        date_str: 日期字符串 (YYYYMMDD)
        time: 时间字符串 (HH:MM:SS)
        
    Returns:
        DataFrame含stock_code, short_name, price, change_pct等
    """
    # 1. 尝试从Redis获取
    try:
        from gs2026.utils.redis_util import _get_redis_client
        redis_client = _get_redis_client()
        
        if redis_client:
            redis_key = f"monitor_gp_sssj_{date_str}:{time}"
            data = redis_client.get(redis_key)
            if data:
                import json
                df = pd.DataFrame(json.loads(data))
                if not df.empty:
                    # 筛选is_zt=1的股票（指定时间点正在涨停）
                    df = df[df['is_zt'] == 1]
                    logger.info(f"从Redis获取涨停股票: {len(df)} 只")
                    return df
    except Exception as e:
        logger.warning(f"Redis查询失败: {e}")
    
    # 2. 从MySQL获取（查询指定时间点正在涨停的股票）
    try:
        table_name = f"monitor_gp_sssj_{date_str}"
        sql = f"""
            SELECT * FROM {table_name}
            WHERE time = '{time}' AND is_zt = 1
        """
        df = pd.read_sql(sql, engine)
        if not df.empty:
            logger.info(f"从MySQL获取涨停股票: {len(df)} 只")
            return df
    except Exception as e:
        logger.warning(f"MySQL查询失败: {e}")
    
    return pd.DataFrame()


def _analyze_ztb_tags(zt_codes: List[str]) -> Dict:
    """分析涨停股票的行业和概念分布（复用stock_picker_service逻辑）
    
    Args:
        zt_codes: 涨停股票代码列表
        
    Returns:
        {'industries': [...], 'concepts': [...]}
    """
    from collections import defaultdict
    
    # 从stock_picker_service导入缓存和搜索器
    from gs2026.dashboard2.services.stock_picker_service import (
        _stock_cache, load_memory_cache, init_pinyin_searcher
    )
    
    # 确保缓存已加载
    if not _stock_cache:
        load_memory_cache()
    
    # 统计行业和概念频次
    industry_counter = defaultdict(int)
    concept_counter = defaultdict(int)
    
    for code in zt_codes:
        stock_data = _stock_cache.get(code)
        if stock_data:
            for ind in stock_data.get('industries', []):
                industry_counter[ind] += 1
            for con in stock_data.get('concepts', []):
                concept_counter[con] += 1
    
    # 构建名称→代码映射
    searcher = init_pinyin_searcher()
    name_to_code = {item['name']: item['code'] for item in searcher.items}
    
    # 按频次降序排列，包含code
    industries = sorted(
        [{'name': name, 'type': 'industry', 'code': name_to_code.get(name, ''), 'count': count}
         for name, count in industry_counter.items()],
        key=lambda x: x['count'], reverse=True
    )
    
    concepts = sorted(
        [{'name': name, 'type': 'concept', 'code': name_to_code.get(name, ''), 'count': count}
         for name, count in concept_counter.items()],
        key=lambda x: x['count'], reverse=True
    )
    
    return {'industries': industries, 'concepts': concepts}


def filter_ztb_snapshot(date: str, time: str, selected_tags: List[Dict], filters: Dict) -> Dict:
    """根据标签筛选股票（查询所有有选中标签的股票，不限涨停）
    
    Args:
        date: 日期字符串 (YYYY-MM-DD)
        time: 时间字符串 (HH:MM:SS)
        selected_tags: 选中的标签 [{'type': 'industry', 'code': '881121', 'name': '半导体'}, ...]
        filters: 筛选条件 {'only_with_bond': bool, 'stock_change': str, 'bond_change': str}
        
    Returns:
        筛选结果（与交叉选股返回格式一致）
    """
    try:
        from collections import defaultdict
        from gs2026.dashboard2.services.stock_picker_service import _stock_cache, load_memory_cache
        
        # 确保缓存已加载
        if not _stock_cache:
            load_memory_cache()
        
        date_str = date.replace('-', '')
        
        # 1. 【修改】从宽表缓存获取所有有选中标签的股票（不限涨停）
        selected_industries_set = set(t['name'] for t in selected_tags if t['type'] == 'industry')
        selected_concepts_set = set(t['name'] for t in selected_tags if t['type'] == 'concept')
        
        stock_matches = {}
        for stock_code, data in _stock_cache.items():
            all_tags = data['industries'] | data['concepts']
            matched = (selected_industries_set | selected_concepts_set) & all_tags
            
            if matched:
                matched_industries = list(selected_industries_set & data['industries'])
                matched_concepts = list(selected_concepts_set & data['concepts'])
                
                stock_matches[stock_code] = {
                    'stock_name': data['stock_name'],
                    'bond_code': data['bond_code'] or '-',
                    'bond_name': data['bond_name'] or '-',
                    'all_industries': list(data['industries']),
                    'matched_industries': matched_industries,
                    'matched_concepts': matched_concepts,
                    'match_count': len(matched_industries) + len(matched_concepts)
                }
        
        if not stock_matches:
            return {'tags': selected_tags, 'groups': [], 'summary': {'total_stocks': 0, 'with_bond': 0, 'query_time_ms': 0}}
        
        logger.info(f"获取匹配标签股票: {date} {time}, 共{len(stock_matches)}只")
        
        # 2. 【修改】查询这些股票在指定时间点的实时价格
        all_codes = list(stock_matches.keys())
        price_data = _query_prices_at_time(all_codes, date_str, time)
        
        # 3. 【修改】查询转债价格（指定时间点）
        bond_codes = [m['bond_code'] for m in stock_matches.values() if m['bond_code'] != '-']
        bond_prices = _get_bond_prices_at_time(date_str, time, bond_codes)
        
        # 4. 【修改】组装结果并分组（与交叉选股一致）
        groups_dict = defaultdict(list)
        with_bond_count = 0
        
        for stock_code, match_info in stock_matches.items():
            price_info = price_data.get(stock_code, {})
            bond_info = bond_prices.get(match_info['bond_code'], {})
            
            # 生成展示文本
            display_lines = match_info['matched_industries'] + match_info['matched_concepts']
            
            stock_result = {
                'stock_code': stock_code,
                'stock_name': match_info['stock_name'] or price_info.get('short_name', ''),
                'change_pct': price_info.get('change_pct', 0),
                'price': price_info.get('price', 0),
                'bond_code': match_info['bond_code'],
                'bond_name': match_info['bond_name'],
                'bond_change_pct': bond_info.get('change_pct', 0),
                'industry_name': '、'.join(match_info['all_industries'][:3]) if match_info['all_industries'] else '',
                'matched_industries': match_info['matched_industries'],
                'matched_concepts': match_info['matched_concepts'],
                'matched_tags_display': '\n'.join(display_lines)
            }
            
            groups_dict[match_info['match_count']].append(stock_result)
            
            if match_info['bond_code'] != '-':
                with_bond_count += 1
        
        # 5. 应用其他筛选条件
        only_with_bond = filters.get('only_with_bond', False)
        
        if only_with_bond:
            for count in list(groups_dict.keys()):
                groups_dict[count] = [s for s in groups_dict[count] if s['bond_code'] and s['bond_code'] != '-']
                if not groups_dict[count]:
                    del groups_dict[count]
            with_bond_count = len([s for count in groups_dict.values() for s in count])
        
        # 6. 构建返回结果（与交叉选股一致）
        result_groups = []
        for count in sorted(groups_dict.keys(), reverse=True):
            stocks = groups_dict[count]
            # 组内按涨跌幅倒排
            stocks.sort(key=lambda x: x['change_pct'], reverse=True)
            
            # 构建标签组合名称
            label_parts = []
            for stock in stocks[:1]:
                for ind in stock['matched_industries']:
                    label_parts.append(f"🏭{ind}")
                for con in stock['matched_concepts']:
                    label_parts.append(f"💡{con}")
            
            if count == len(selected_tags) and selected_tags:
                label = f"命中全部 {count} 个"
            elif selected_tags:
                label = f"命中 {count} 个"
            else:
                label = f"涨停股票 ({len(stocks)}只)"
            
            result_groups.append({
                'match_count': count,
                'label': label,
                'stocks': stocks
            })
        
        total = sum(len(stocks) for stocks in groups_dict.values())
        
        return {
            'tags': selected_tags,  # 添加tags字段，与交叉选股格式一致
            'groups': result_groups,
            'summary': {
                'total_stocks': total,  # 改为total_stocks，与交叉选股一致
                'with_bond': with_bond_count,
                'query_time_ms': 0
            }
        }
    except Exception as e:
        logger.error(f"筛选涨停股票失败: {e}")
        return {'groups': [], 'summary': {'total': 0, 'with_bond': 0, 'query_time_ms': 0}}


def _get_stock_details_batch(stock_codes: List[str]) -> Dict[str, Dict]:
    """批量获取股票详情（行业、概念、债券）- 使用宽表缓存"""
    try:
        # 从stock_picker_service导入宽表缓存
        from gs2026.dashboard2.services.stock_picker_service import _stock_cache, load_memory_cache
        
        # 确保缓存已加载
        if not _stock_cache:
            load_memory_cache()
        
        # 从宽表缓存获取数据
        result = {}
        for code in stock_codes:
            data = _stock_cache.get(code)
            if data:
                result[code] = {
                    'stock_name': data.get('stock_name', ''),
                    'industry_name': list(data['industries'])[0] if data.get('industries') else '-',
                    'industry_names': list(data.get('industries', set())),
                    'concepts': list(data.get('concepts', set())),
                    'bond_code': data.get('bond_code', '-'),
                    'bond_name': data.get('bond_name', '-'),
                }
            else:
                # 缓存中没有，返回默认值
                result[code] = {
                    'stock_name': '',
                    'industry_name': '-',
                    'industry_names': [],
                    'concepts': [],
                    'bond_code': '-',
                    'bond_name': '-',
                }
        
        return result
    except Exception as e:
        logger.error(f"获取股票详情失败: {e}")
        return {code: {
            'stock_name': '',
            'industry_name': '-',
            'industry_names': [],
            'concepts': [],
            'bond_code': '-',
            'bond_name': '-',
        } for code in stock_codes}


def _get_bond_prices_at_time(date_str: str, time: str, bond_codes: List[str]) -> Dict[str, Dict]:
    """获取指定时间点的转债价格"""
    if not bond_codes:
        return {}
    
    result = {}
    
    # 1. 尝试从Redis获取
    try:
        from gs2026.utils.redis_util import _get_redis_client
        redis_client = _get_redis_client()
        
        if redis_client:
            redis_key = f"monitor_zq_sssj_{date_str}:{time}"
            data = redis_client.get(redis_key)
            if data:
                import json
                df = pd.DataFrame(json.loads(data))
                if not df.empty:
                    for _, row in df.iterrows():
                        if row['bond_code'] in bond_codes:
                            result[row['bond_code']] = {
                                'price': float(row.get('price', 0)),
                                'change_pct': float(row.get('change_pct', 0))
                            }
                    logger.info(f"从Redis获取转债价格: {len(result)} 只")
                    return result
    except Exception as e:
        logger.warning(f"Redis查询转债失败: {e}")
    
    # 2. 从MySQL获取
    try:
        table_name = f"monitor_zq_sssj_{date_str}"
        placeholders = ','.join([f"'{code}'" for code in bond_codes])
        sql = f"""
            SELECT bond_code, price, change_pct
            FROM {table_name}
            WHERE time = '{time}' AND bond_code IN ({placeholders})
        """
        df = pd.read_sql(sql, engine)
        for _, row in df.iterrows():
            result[row['bond_code']] = {
                'price': float(row['price']),
                'change_pct': float(row['change_pct'])
            }
        logger.info(f"从MySQL获取转债价格: {len(result)} 只")
    except Exception as e:
        logger.warning(f"MySQL查询转债失败: {e}")
    
    return result


def _query_prices_at_time(stock_codes: List[str], date_str: str, time: str) -> Dict[str, Dict]:
    """查询指定时间点的股票价格（先Redis后MySQL）
    
    Args:
        stock_codes: 股票代码列表
        date_str: 日期字符串 (YYYYMMDD)
        time: 时间字符串 (HH:MM:SS)
        
    Returns:
        {stock_code: {'price': float, 'change_pct': float, 'short_name': str}, ...}
    """
    if not stock_codes:
        return {}
    
    result = {}
    
    # 1. 尝试从Redis获取
    try:
        from gs2026.utils.redis_util import _get_redis_client
        redis_client = _get_redis_client()
        
        if redis_client:
            redis_key = f"monitor_gp_sssj_{date_str}:{time}"
            data = redis_client.get(redis_key)
            if data:
                import json
                df = pd.DataFrame(json.loads(data))
                if not df.empty:
                    for _, row in df.iterrows():
                        if row['stock_code'] in stock_codes:
                            result[row['stock_code']] = {
                                'price': float(row.get('price', 0)),
                                'change_pct': float(row.get('change_pct', 0)),
                                'short_name': row.get('short_name', '')
                            }
                    logger.info(f"从Redis获取股票价格: {len(result)} 只")
                    return result
    except Exception as e:
        logger.warning(f"Redis查询价格失败: {e}")
    
    # 2. 从MySQL获取
    try:
        table_name = f"monitor_gp_sssj_{date_str}"
        placeholders = ','.join([f"'{code}'" for code in stock_codes])
        sql = f"""
            SELECT stock_code, short_name, price, change_pct
            FROM {table_name}
            WHERE time = '{time}' AND stock_code IN ({placeholders})
        """
        df = pd.read_sql(sql, engine)
        for _, row in df.iterrows():
            result[row['stock_code']] = {
                'price': float(row['price']),
                'change_pct': float(row['change_pct']),
                'short_name': row['short_name']
            }
        logger.info(f"从MySQL获取股票价格: {len(result)} 只")
    except Exception as e:
        logger.error(f"MySQL查询价格失败: {e}")
    
    return result
