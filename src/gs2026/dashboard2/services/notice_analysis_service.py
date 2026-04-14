"""公告分析服务层"""

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


def get_notice_list(
    date: str = None,
    stock_code: str = None,
    stock_name: str = None,
    search: str = None,
    risk_level: str = None,
    notice_type: str = None,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """获取公告列表"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        notice_date = date_obj.strftime('%Y-%m-%d')
        
        where_clauses = [f"notice_date = '{notice_date}'"]
        
        if stock_code:
            where_clauses.append(f"stock_code = '{stock_code}'")
        if stock_name:
            where_clauses.append(f"stock_name LIKE '%{stock_name}%'")
        if risk_level:
            where_clauses.append(f"risk_level = '{risk_level}'")
        if notice_type:
            where_clauses.append(f"notice_type = '{notice_type}'")
        if search:
            where_clauses.append(f"MATCH(notice_title, notice_content, judgment_basis) AGAINST('{search}' IN BOOLEAN MODE)")
        
        where_sql = " AND ".join(where_clauses)
        offset = (page - 1) * page_size
        
        sql = f"""
            SELECT SQL_CALC_FOUND_ROWS 
                content_hash, notice_id, stock_code, stock_name, notice_date,
                notice_title, risk_level, notice_type, judgment_basis, key_points,
                short_term_impact, medium_term_impact, risk_score, type_score
            FROM analysis_notice_detail_2026
            WHERE {where_sql}
            ORDER BY notice_date DESC
            LIMIT {page_size} OFFSET {offset}
        """
        
        df = pd.read_sql(sql, engine)
        
        total_sql = "SELECT FOUND_ROWS() as total"
        total_df = pd.read_sql(total_sql, engine)
        total = int(total_df.iloc[0]['total']) if not total_df.empty else 0
        
        items = []
        for _, row in df.iterrows():
            item = row.to_dict()
            # 处理日期格式
            if item.get('notice_date') is not None:
                item['notice_date'] = str(item['notice_date'])
            # 处理JSON字段
            for key in ('judgment_basis', 'key_points'):
                try:
                    val = item.get(key)
                    if val and val != 'null':
                        item[key] = json.loads(val)
                    else:
                        item[key] = []
                except:
                    item[key] = []
            items.append(item)
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size}
    except Exception as e:
        logger.error(f"公告列表查询失败: {e}")
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}


def get_notice_detail(content_hash: str) -> Optional[Dict]:
    """获取公告详情"""
    try:
        sql = f"SELECT * FROM analysis_notice_detail_2026 WHERE content_hash = '{content_hash}' LIMIT 1"
        df = pd.read_sql(sql, engine)
        if not df.empty:
            item = df.iloc[0].to_dict()
            try:
                item['key_points'] = json.loads(item.get('key_points', '[]'))
            except:
                item['key_points'] = []
            return item
    except Exception as e:
        logger.error(f"公告详情查询失败: {e}")
    return None


def get_notice_stats(date: str = None) -> Dict:
    """获取公告统计（当日统计）
    
    Returns:
        {
            'total': 总公告数,
            '利好': 利好公告数,
            '利空': 利空公告数,
            '中性': 中性公告数
        }
    """
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        notice_date = date_obj.strftime('%Y-%m-%d')
        
        sql = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN notice_type = '利好' THEN 1 ELSE 0 END) as 利好,
                SUM(CASE WHEN notice_type = '利空' THEN 1 ELSE 0 END) as 利空,
                SUM(CASE WHEN notice_type = '中性' THEN 1 ELSE 0 END) as 中性
            FROM analysis_notice_detail_2026
            WHERE notice_date = '{notice_date}'
        """
        
        df = pd.read_sql(sql, engine)
        if not df.empty:
            row = df.iloc[0]
            return {
                'total': int(row['total']),
                '利好': int(row['利好']),
                '利空': int(row['利空']),
                '中性': int(row['中性'])
            }
    except Exception as e:
        logger.error(f"公告统计查询失败: {e}")
    
    return {'total': 0, '利好': 0, '利空': 0, '中性': 0}
