"""领域分析服务层 - 业务逻辑与缓存管理

职责:
    1. 领域事件列表查询（Redis优先+MySQL回源）
    2. 单条领域事件详情查询
    3. 领域统计信息
    4. 热门板块排行

缓存策略:
    - Redis: 48h TTL（详情），72h TTL（时间线/索引）
    - MySQL: 永久存储，回源时更新Redis
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pandas as pd
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, log_util, redis_util
from gs2026.utils import mysql_util as mu

logger = log_util.setup_logger(__name__)

# 配置
url: str = config_util.get_config('common.url')
redis_host: str = config_util.get_config('common.redis.host', 'localhost')
redis_port: int = int(config_util.get_config('common.redis.port', 6379))

mysql_tool = mu.MysqlTool(url)
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# TTL配置
DETAIL_TTL = 48 * 3600
TIMELINE_TTL = 48 * 3600


def _ensure_redis():
    """确保Redis已初始化"""
    try:
        redis_util._get_redis_client()
    except RuntimeError:
        redis_util.init_redis(host=redis_host, port=int(redis_port), decode_responses=False)


def _decode(val):
    """bytes → str"""
    if isinstance(val, bytes):
        return val.decode('utf-8')
    return val


def get_domain_list(
    date: str = None,
    main_area: str = None,
    child_area: str = None,
    search: str = None,
    news_type: str = None,
    news_size: str = None,
    min_score: int = 0,
    sector: str = None,
    concept: str = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = 'time'
) -> Dict[str, Any]:
    """获取领域事件列表"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    # 尝试Redis
    try:
        result = _get_list_from_redis(date, main_area, child_area, news_type, news_size, 
                                      sector, concept, page, page_size, sort_by, min_score)
        if result and result.get('items'):
            result['source'] = 'redis'
            return result
    except Exception as e:
        logger.debug(f"Redis读取失败，回源MySQL: {e}")
    
    # 回源MySQL
    result = _get_list_from_mysql(date, main_area, child_area, search, news_type, news_size,
                                  sector, concept, page, page_size, sort_by, min_score)
    result['source'] = 'mysql'
    return result


def _get_list_from_redis(date, main_area, child_area, news_type, news_size,
                         sector, concept, page, page_size, sort_by, min_score):
    """从Redis获取领域事件列表"""
    _ensure_redis()
    client = redis_util._get_redis_client()
    
    # 确定使用的key
    if main_area and child_area:
        key = f"domain:area:{main_area}:{child_area}"
        hashes = client.smembers(key)
    elif news_type:
        key = f"domain:type:{date}:{news_type}"
        hashes = client.zrevrange(key, 0, -1)
    else:
        key = f"domain:timeline:{date}"
        hashes = client.zrevrange(key, 0, -1)
    
    if not hashes:
        return None
    
    # 获取详情并过滤
    items = []
    for h in hashes:
        content_hash = _decode(h)
        detail = client.hgetall(f"domain:detail:{content_hash}")
        if not detail:
            continue
        
        item = {k.decode(): v.decode() for k, v in detail.items()}
        
        # 评分过滤
        if min_score > 0 and int(item.get('composite_score', 0)) < min_score:
            continue
        
        # 大小过滤
        if news_size and item.get('news_size') != news_size:
            continue
        
        # 板块过滤
        if sector:
            sectors = json.loads(item.get('sectors', '[]'))
            if sector not in sectors:
                continue
        
        # 概念过滤
        if concept:
            concepts = json.loads(item.get('concepts', '[]'))
            if concept not in concepts:
                continue
        
        # 解析JSON字段
        for key in ('sectors', 'concepts', 'stock_codes', 'deep_analysis'):
            try:
                item[key] = json.loads(item.get(key, '[]'))
            except:
                item[key] = []
        
        items.append(item)
    
    # 排序
    if sort_by == 'score':
        items.sort(key=lambda x: int(x.get('composite_score', 0)), reverse=True)
    else:
        items.sort(key=lambda x: x.get('event_time', ''), reverse=True)
    
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        'items': items[start:end],
        'total': total,
        'page': page,
        'page_size': page_size
    }


def _get_list_from_mysql(date, main_area, child_area, search, news_type, news_size,
                         sector, concept, page, page_size, sort_by, min_score):
    """从MySQL获取领域事件列表"""
    # 构建查询
    where_clauses = ["1=1"]
    
    if main_area:
        where_clauses.append(f"main_area = '{main_area}'")
    if child_area:
        where_clauses.append(f"child_area = '{child_area}'")
    if news_type:
        where_clauses.append(f"news_type = '{news_type}'")
    if news_size:
        where_clauses.append(f"news_size = '{news_size}'")
    if min_score > 0:
        where_clauses.append(f"composite_score >= {min_score}")
    
    # 日期范围
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        start_time = date_obj.strftime('%Y-%m-%d 00:00:00')
        end_time = date_obj.strftime('%Y-%m-%d 23:59:59')
        where_clauses.append(f"event_time BETWEEN '{start_time}' AND '{end_time}'")
    except:
        pass
    
    # 全文搜索
    if search:
        where_clauses.append(f"(MATCH(key_event, brief_desc, reason_analysis) AGAINST('{search}' IN BOOLEAN MODE))")
    
    # 板块/概念JSON搜索
    if sector:
        where_clauses.append(f"JSON_CONTAINS(sectors, '\"{sector}\"')")
    if concept:
        where_clauses.append(f"JSON_CONTAINS(concepts, '\"{concept}\"')")
    
    where_sql = " AND ".join(where_clauses)
    
    # 排序
    order_by = "event_time DESC" if sort_by == 'time' else "composite_score DESC, event_time DESC"
    
    # 分页查询
    offset = (page - 1) * page_size
    
    sql = f"""
        SELECT SQL_CALC_FOUND_ROWS 
            content_hash, main_area, child_area, event_time, event_source,
            key_event, brief_desc, importance_score, business_impact_score, composite_score,
            news_size, news_type, sectors, concepts, stock_codes, reason_analysis, deep_analysis
        FROM analysis_domain_detail_2026
        WHERE {where_sql}
        ORDER BY {order_by}
        LIMIT {page_size} OFFSET {offset}
    """
    
    try:
        df = pd.read_sql(sql, engine)
        
        # 获取总数
        total_sql = f"SELECT FOUND_ROWS() as total"
        total_df = pd.read_sql(total_sql, engine)
        total = int(total_df.iloc[0]['total']) if not total_df.empty else 0
        
        # 解析JSON字段
        items = []
        for _, row in df.iterrows():
            item = row.to_dict()
            for key in ('sectors', 'concepts', 'stock_codes', 'deep_analysis'):
                try:
                    item[key] = json.loads(item.get(key, '[]'))
                except:
                    item[key] = []
            items.append(item)
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size
        }
    except Exception as e:
        logger.error(f"MySQL查询失败: {e}")
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}


def get_domain_detail(content_hash: str) -> Optional[Dict]:
    """获取单条领域事件详情"""
    # 尝试Redis
    try:
        _ensure_redis()
        client = redis_util._get_redis_client()
        detail = client.hgetall(f"domain:detail:{content_hash}")
        if detail:
            item = {k.decode(): v.decode() for k, v in detail.items()}
            for key in ('sectors', 'concepts', 'stock_codes', 'deep_analysis'):
                try:
                    item[key] = json.loads(item.get(key, '[]'))
                except:
                    item[key] = []
            item['source'] = 'redis'
            return item
    except Exception as e:
        logger.debug(f"Redis读取失败: {e}")
    
    # 回源MySQL
    try:
        sql = f"""
            SELECT * FROM analysis_domain_detail_2026 
            WHERE content_hash = '{content_hash}'
            LIMIT 1
        """
        df = pd.read_sql(sql, engine)
        if not df.empty:
            item = df.iloc[0].to_dict()
            for key in ('sectors', 'concepts', 'stock_codes', 'deep_analysis'):
                try:
                    item[key] = json.loads(item.get(key, '[]'))
                except:
                    item[key] = []
            item['source'] = 'mysql'
            return item
    except Exception as e:
        logger.error(f"MySQL查询失败: {e}")
    
    return None


def get_domain_stats(date: str = None, main_area: str = None) -> Dict:
    """获取领域统计信息"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        start_time = date_obj.strftime('%Y-%m-%d 00:00:00')
        end_time = date_obj.strftime('%Y-%m-%d 23:59:59')
        
        where_clause = f"event_time BETWEEN '{start_time}' AND '{end_time}'"
        if main_area:
            where_clause += f" AND main_area = '{main_area}'"
        
        sql = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN news_type = '利好' THEN 1 ELSE 0 END) as good_count,
                SUM(CASE WHEN news_type = '利空' THEN 1 ELSE 0 END) as bad_count,
                SUM(CASE WHEN news_type = '中性' THEN 1 ELSE 0 END) as neutral_count,
                AVG(composite_score) as avg_score,
                MAX(composite_score) as max_score
            FROM analysis_domain_detail_2026
            WHERE {where_clause}
        """
        
        df = pd.read_sql(sql, engine)
        if not df.empty:
            row = df.iloc[0]
            return {
                'total': int(row['total']),
                'good_count': int(row['good_count']),
                'bad_count': int(row['bad_count']),
                'neutral_count': int(row['neutral_count']),
                'avg_score': float(row['avg_score']) if row['avg_score'] else 0,
                'max_score': int(row['max_score']) if row['max_score'] else 0
            }
    except Exception as e:
        logger.error(f"统计查询失败: {e}")
    
    return {'total': 0, 'good_count': 0, 'bad_count': 0, 'neutral_count': 0, 
            'avg_score': 0, 'max_score': 0}


def get_areas() -> List[Dict]:
    """获取领域列表（主领域+子领域）"""
    try:
        sql = """
            SELECT DISTINCT main_area, child_area 
            FROM analysis_domain_detail_2026 
            ORDER BY main_area, child_area
        """
        df = pd.read_sql(sql, engine)
        
        areas = {}
        for _, row in df.iterrows():
            main = row['main_area']
            child = row['child_area']
            if main not in areas:
                areas[main] = []
            areas[main].append(child)
        
        return [{'main_area': k, 'child_areas': v} for k, v in areas.items()]
    except Exception as e:
        logger.error(f"领域列表查询失败: {e}")
        return []


def get_hot_sectors(date: str = None, top: int = 10) -> List[Dict]:
    """获取热门板块排行"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    try:
        date_obj = datetime.strptime(date, '%Y%m%d')
        start_time = date_obj.strftime('%Y-%m-%d 00:00:00')
        end_time = date_obj.strftime('%Y-%m-%d 23:59:59')
        
        sql = f"""
            SELECT 
                JSON_UNQUOTE(JSON_EXTRACT(sectors, '$[0]')) as sector,
                COUNT(*) as count,
                AVG(composite_score) as avg_score
            FROM analysis_domain_detail_2026
            WHERE event_time BETWEEN '{start_time}' AND '{end_time}'
                AND sectors IS NOT NULL
            GROUP BY JSON_UNQUOTE(JSON_EXTRACT(sectors, '$[0]'))
            HAVING sector IS NOT NULL
            ORDER BY count DESC, avg_score DESC
            LIMIT {top}
        """
        
        df = pd.read_sql(sql, engine)
        return df.to_dict('records')
    except Exception as e:
        logger.error(f"热门板块查询失败: {e}")
        return []
