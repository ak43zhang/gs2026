"""涨停分析服务层"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
from sqlalchemy import create_engine

from gs2026.utils import config_util, log_util, redis_util
from gs2026.utils import mysql_util as mu

logger = log_util.setup_logger(__name__)

url = config_util.get_config('common.url')
redis_host = config_util.get_config('common.redis.host', 'localhost')
redis_port = int(config_util.get_config('common.redis.port', 6379))

mysql_tool = mu.MysqlTool(url)
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

DETAIL_TTL = 48 * 3600
TIMELINE_TTL = 72 * 3600


def _ensure_redis():
    try:
        redis_util._get_redis_client()
    except RuntimeError:
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
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """获取涨停列表"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    # 根据日期确定表名
    table_year = date[:4] if len(date) >= 4 else '2026'
    table_name = f"analysis_ztb_detail_{table_year}"
    
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        trade_date = date_obj.strftime('%Y-%m-%d')
        
        where_clauses = [f"trade_date = '{trade_date}'"]
        
        if stock_name:
            where_clauses.append(f"stock_name LIKE '%{stock_name}%'")
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
        
        where_sql = " AND ".join(where_clauses)
        offset = (page - 1) * page_size
        
        sql = f"""
            SELECT SQL_CALC_FOUND_ROWS 
                content_hash, stock_name, stock_code, trade_date, zt_time,
                stock_nature, lhb_analysis, sectors, concepts, leading_stocks,
                has_expect, continuity, zt_time_range
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY zt_time ASC
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
                if hasattr(item['zt_time'], 'total_seconds'):
                    # Timedelta 类型
                    total_seconds = int(item['zt_time'].total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    item['zt_time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    item['zt_time'] = str(item['zt_time'])
            # 转换日期字段为字符串
            if item.get('trade_date') is not None:
                item['trade_date'] = str(item['trade_date'])
            for key in ('sectors', 'concepts', 'leading_stocks'):
                try:
                    item[key] = json.loads(item.get(key, '[]'))
                except:
                    item[key] = []
            items.append(item)
        
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size}
    except Exception as e:
        logger.error(f"涨停列表查询失败: {e}")
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}


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
                if hasattr(item['zt_time'], 'total_seconds'):
                    total_seconds = int(item['zt_time'].total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    item['zt_time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    item['zt_time'] = str(item['zt_time'])
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
    """获取涨停统计"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    # 根据日期确定表名
    table_year = date[:4] if len(date) >= 4 else datetime.now().strftime('%Y')
    table_name = f"analysis_ztb_detail_{table_year}"
    
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        trade_date = date_obj.strftime('%Y-%m-%d')
        
        sql = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN zt_time_range = 'early' THEN 1 ELSE 0 END) as early_count,
                SUM(CASE WHEN zt_time_range = 'mid' THEN 1 ELSE 0 END) as mid_count,
                SUM(CASE WHEN zt_time_range = 'late' THEN 1 ELSE 0 END) as late_count,
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
                'early_count': int(row['early_count']),
                'mid_count': int(row['mid_count']),
                'late_count': int(row['late_count']),
                'expect_count': int(row['expect_count']),
                'continuity_count': int(row['continuity_count'])
            }
    except Exception as e:
        logger.error(f"涨停统计查询失败: {e}")
    
    return {'total': 0, 'early_count': 0, 'mid_count': 0, 'late_count': 0, 
            'expect_count': 0, 'continuity_count': 0}


def get_hot_sectors(date: str = None, top: int = 10) -> List[Dict]:
    """获取热门板块"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
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
