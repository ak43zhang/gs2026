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
    client = redis_util._get_redis_client()
    if client is None:
        redis_util.init_redis(host=redis_host, port=int(redis_port), decode_responses=False)


def _decode(val):
    if isinstance(val, bytes):
        return val.decode('utf-8')
    return val


def _calc_grade(score) -> str:
    """根据overnight_score计算评分档位"""
    score = score or 0
    if score >= 85:
        return 'S'
    elif score >= 70:
        return 'A'
    elif score >= 50:
        return 'B'
    elif score >= 30:
        return 'C'
    else:
        return 'D'


def _grade_to_range(grade: str):
    """评分档位转为overnight_score范围 (min, max)"""
    return {'S': (85, 100), 'A': (70, 84), 'B': (50, 69), 'C': (30, 49), 'D': (0, 29)}.get(grade)


def _process_item(item: dict) -> dict:
    """统一处理单条公告记录：日期格式化、JSON解析、评分档位"""
    if item.get('notice_date') is not None:
        item['notice_date'] = str(item['notice_date'])
    if item.get('analysis_time') is not None:
        item['analysis_time'] = str(item['analysis_time'])
    for key in ('judgment_basis', 'key_points'):
        try:
            val = item.get(key)
            if val and val != 'null':
                if isinstance(val, str):
                    item[key] = json.loads(val)
                elif isinstance(val, list):
                    pass
                else:
                    item[key] = []
            else:
                item[key] = []
        except Exception:
            item[key] = []
    item['grade'] = _calc_grade(item.get('overnight_score', 0))
    return item


# ==================== V3 新增API ====================

def get_notice_top_signals(date: str = None, limit: int = 5) -> Dict[str, List]:
    """顶级信号快览：4个组合(高+利好/高+利空/中+利好/中+利空)各Top N"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        notice_date = date_obj.strftime('%Y-%m-%d')

        combos = [
            ('bullish', '高', '利好'),
            ('bearish', '高', '利空'),
            ('mid_bullish', '中', '利好'),
            ('mid_bearish', '中', '利空'),
        ]
        result = {}
        for key, risk, ntype in combos:
            sql = f"""
                SELECT content_hash, stock_code, stock_name, notice_title,
                       risk_level, notice_type, notice_category,
                       overnight_score, market_expectation, open_prediction,
                       duration, overnight_strategy, risk_score, type_score,
                       key_points, notice_date
                FROM analysis_notice_detail_2026
                WHERE notice_date = '{notice_date}'
                  AND risk_level = '{risk}' AND notice_type = '{ntype}'
                ORDER BY overnight_score DESC
                LIMIT {limit}
            """
            df = pd.read_sql(sql, engine)
            items = [_process_item(row.to_dict()) for _, row in df.iterrows()]
            result[key] = items
        return result
    except Exception as e:
        logger.error(f"顶级信号查询失败: {e}")
        return {'bullish': [], 'bearish': [], 'mid_bullish': [], 'mid_bearish': []}


def get_notice_categories(date: str = None) -> List[str]:
    """获取公告分类动态列表"""
    try:
        where = ""
        if date:
            date_obj = datetime.strptime(date, '%Y%m%d')
            notice_date = date_obj.strftime('%Y-%m-%d')
            where = f"WHERE notice_date = '{notice_date}'"
        sql = f"""
            SELECT DISTINCT notice_category
            FROM analysis_notice_detail_2026
            {where}
            ORDER BY notice_category
        """
        df = pd.read_sql(sql, engine)
        cats = [str(c) for c in df['notice_category'].dropna().tolist() if c and str(c).strip()]
        return cats
    except Exception as e:
        logger.error(f"公告分类查询失败: {e}")
        return []


def get_notice_stats_v2(date: str = None) -> Dict:
    """增强版统计：基础+评分档位+超短维度"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        notice_date = date_obj.strftime('%Y-%m-%d')

        sql = f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN notice_type = '利好' THEN 1 ELSE 0 END) as bullish,
                SUM(CASE WHEN notice_type = '利空' THEN 1 ELSE 0 END) as bearish,
                SUM(CASE WHEN notice_type = '中性' THEN 1 ELSE 0 END) as neutral,
                SUM(CASE WHEN overnight_score >= 85 THEN 1 ELSE 0 END) as grade_s,
                SUM(CASE WHEN overnight_score >= 70 AND overnight_score < 85 THEN 1 ELSE 0 END) as grade_a,
                SUM(CASE WHEN overnight_score >= 50 AND overnight_score < 70 THEN 1 ELSE 0 END) as grade_b,
                SUM(CASE WHEN overnight_score >= 30 AND overnight_score < 50 THEN 1 ELSE 0 END) as grade_c,
                SUM(CASE WHEN overnight_score < 30 OR overnight_score IS NULL THEN 1 ELSE 0 END) as grade_d,
                SUM(CASE WHEN market_expectation LIKE '%%超预期%%' THEN 1 ELSE 0 END) as expect_super,
                SUM(CASE WHEN open_prediction LIKE '%%大幅高开%%' OR open_prediction LIKE '%%大幅低开%%' THEN 1 ELSE 0 END) as big_gap,
                SUM(CASE WHEN duration LIKE '%%持续发酵%%' THEN 1 ELSE 0 END) as lasting,
                SUM(CASE WHEN risk_level = '高' AND notice_type = '利好' THEN 1 ELSE 0 END) as high_bullish,
                SUM(CASE WHEN risk_level = '高' AND notice_type = '利空' THEN 1 ELSE 0 END) as high_bearish
            FROM analysis_notice_detail_2026
            WHERE notice_date = '{notice_date}'
        """
        df = pd.read_sql(sql, engine)
        if not df.empty:
            r = df.iloc[0]
            return {
                'total': int(r['total']),
                '利好': int(r['bullish']), '利空': int(r['bearish']), '中性': int(r['neutral']),
                'grade_dist': {
                    'S': int(r['grade_s']), 'A': int(r['grade_a']),
                    'B': int(r['grade_b']), 'C': int(r['grade_c']), 'D': int(r['grade_d'])
                },
                'super_expect': int(r['expect_super']),
                'big_gap': int(r['big_gap']),
                'lasting': int(r['lasting']),
                'high_bullish': int(r['high_bullish']),
                'high_bearish': int(r['high_bearish']),
            }
    except Exception as e:
        logger.error(f"增强统计查询失败: {e}")
    return {'total': 0, '利好': 0, '利空': 0, '中性': 0,
            'grade_dist': {'S': 0, 'A': 0, 'B': 0, 'C': 0, 'D': 0},
            'super_expect': 0, 'big_gap': 0, 'lasting': 0,
            'high_bullish': 0, 'high_bearish': 0}


# ==================== 原有API（增强兼容） ====================

def get_notice_list(
    date: str = None,
    stock_code: str = None,
    stock_name: str = None,
    search: str = None,
    risk_level: str = None,
    notice_type: str = None,
    notice_category: str = None,
    market_expectation: str = None,
    open_prediction: str = None,
    duration: str = None,
    grade: str = None,
    sort_by: str = 'score_desc',
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """获取公告列表（V3增强版，兼容V2调用）"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')

    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        notice_date = date_obj.strftime('%Y-%m-%d')

        where_clauses = [f"notice_date = '{notice_date}'"]

        if stock_code:
            where_clauses.append(f"stock_code = '{stock_code}'")
        if stock_name:
            where_clauses.append(f"stock_name LIKE '%%{stock_name}%%'")
        if risk_level:
            where_clauses.append(f"risk_level = '{risk_level}'")
        if notice_type:
            where_clauses.append(f"notice_type = '{notice_type}'")
        if notice_category:
            where_clauses.append(f"notice_category = '{notice_category}'")
        if market_expectation:
            where_clauses.append(f"market_expectation LIKE '%%{market_expectation}%%'")
        if open_prediction:
            where_clauses.append(f"open_prediction LIKE '%%{open_prediction}%%'")
        if duration:
            where_clauses.append(f"duration LIKE '%%{duration}%%'")
        if grade:
            rng = _grade_to_range(grade)
            if rng:
                where_clauses.append(f"overnight_score >= {rng[0]} AND overnight_score <= {rng[1]}")
        if search:
            where_clauses.append(f"(notice_title LIKE '%%{search}%%' OR stock_name LIKE '%%{search}%%' OR stock_code LIKE '%%{search}%%')")

        where_sql = " AND ".join(where_clauses)
        offset = (page - 1) * page_size

        # 排序
        order_map = {
            'score_desc': 'overnight_score DESC, risk_score DESC',
            'score_asc': 'overnight_score ASC',
            'risk_desc': 'risk_score DESC, overnight_score DESC',
            'time_desc': 'analysis_time DESC',
        }
        order_by = order_map.get(sort_by, 'overnight_score DESC, risk_score DESC')

        sql = f"""
            SELECT SQL_CALC_FOUND_ROWS
                content_hash, notice_id, stock_code, stock_name, notice_date,
                notice_title, risk_level, notice_type, notice_category,
                judgment_basis, key_points,
                short_term_impact, medium_term_impact,
                risk_score, type_score, overnight_score,
                market_expectation, open_prediction, duration, overnight_strategy
            FROM analysis_notice_detail_2026
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT {page_size} OFFSET {offset}
        """

        df = pd.read_sql(sql, engine)

        total_sql = "SELECT FOUND_ROWS() as total"
        total_df = pd.read_sql(total_sql, engine)
        total = int(total_df.iloc[0]['total']) if not total_df.empty else 0

        items = [_process_item(row.to_dict()) for _, row in df.iterrows()]
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size}
    except Exception as e:
        logger.error(f"公告列表查询失败: {e}")
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}


def get_notice_detail(content_hash: str) -> Optional[Dict]:
    """获取公告详情（返回全部字段）"""
    try:
        sql = f"SELECT * FROM analysis_notice_detail_2026 WHERE content_hash = '{content_hash}' LIMIT 1"
        df = pd.read_sql(sql, engine)
        if not df.empty:
            item = df.iloc[0].to_dict()
            # 移除自增id，不暴露给前端
            item.pop('id', None)
            return _process_item(item)
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
