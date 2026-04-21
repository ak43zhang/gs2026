#!/usr/bin/env python3
"""
行业概念交叉选股服务层
提供拼音搜索、宽表缓存、交叉选股查询功能
"""
import json
import logging
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from collections import defaultdict

import pandas as pd
from pypinyin import lazy_pinyin, Style
from sqlalchemy import text

from gs2026.utils import mysql_util, config_util

logger = logging.getLogger(__name__)

# 内存缓存
_stock_cache: Dict[str, dict] = {}
_pinyin_searcher = None
_bond_map: Dict[str, dict] = {}

# 配置
redis_host = config_util.get_config('redis.host') or 'localhost'
redis_port = config_util.get_config('redis.port') or 6379


class PinyinSearcher:
    """拼音搜索器"""
    
    def __init__(self):
        self.items: List[dict] = []
    
    def add(self, name: str, code: str, item_type: str):
        """添加搜索项"""
        pinyin_full = ''.join(lazy_pinyin(name))
        pinyin_initials = ''.join(lazy_pinyin(name, style=Style.FIRST_LETTER))
        self.items.append({
            'name': name,
            'code': code,
            'type': item_type,  # 'industry' 或 'concept'
            'pinyin_full': pinyin_full.lower(),
            'pinyin_initials': pinyin_initials.lower(),
            'name_lower': name.lower()
        })
    
    def search(self, query: str, limit: int = 20) -> List[dict]:
        """搜索"""
        query = query.lower().strip()
        results = []
        
        for item in self.items:
            if (query in item['name_lower'] or 
                query in item['pinyin_full'] or 
                query in item['pinyin_initials']):
                results.append({
                    'name': item['name'],
                    'code': item['code'],
                    'type': item['type']
                })
        
        return results[:limit]


def init_pinyin_searcher() -> PinyinSearcher:
    """初始化拼音搜索器"""
    global _pinyin_searcher
    
    if _pinyin_searcher is not None:
        return _pinyin_searcher
    
    _pinyin_searcher = PinyinSearcher()
    
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        
        # 加载行业
        with mysql_tool.engine.connect() as conn:
            industries = pd.read_sql("SELECT name, code FROM data_industry_code_ths", conn).to_dict('records')
        for row in industries:
            _pinyin_searcher.add(row['name'], row['code'], 'industry')
        
        # 加载概念（使用 data_gnzsxx_ths 表，886代码体系）
        with mysql_tool.engine.connect() as conn:
            concepts = pd.read_sql(
                "SELECT DISTINCT name, index_code as code FROM data_gnzsxx_ths", 
                conn
            ).to_dict('records')
        for row in concepts:
            _pinyin_searcher.add(row['name'], row['code'], 'concept')
        
        logger.info(f"拼音搜索器初始化完成: {len(_pinyin_searcher.items)} 条记录")
        
    except Exception as e:
        logger.error(f"拼音搜索器初始化失败: {e}")
    
    return _pinyin_searcher


def search_tags(query: str, limit: int = 20) -> List[dict]:
    """搜索行业/概念"""
    searcher = init_pinyin_searcher()
    return searcher.search(query, limit)


def warm_up_cache():
    """预热宽表缓存"""
    logger.info("开始预热宽表缓存...")
    
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        
        # 1. 加载所有股票的行业归属
        industry_stocks = defaultdict(lambda: {'codes': [], 'names': []})
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(
                "SELECT stock_code, code as industry_code, name as industry_name FROM data_industry_code_component_ths",
                conn
            ).to_dict('records')
        for row in rows:
            industry_stocks[row['stock_code']]['codes'].append(row['industry_code'])
            industry_stocks[row['stock_code']]['names'].append(row['industry_name'])
        
        # 2. 加载概念名称映射（使用 data_gnzsxx_ths 表，886代码体系）
        concept_name_map = {}
        with mysql_tool.engine.connect() as conn:
            concept_rows = pd.read_sql(
                "SELECT DISTINCT index_code, name FROM data_gnzsxx_ths", 
                conn
            ).to_dict('records')
        for row in concept_rows:
            concept_name_map[row['index_code']] = row['name']
        
        # 3. 加载所有股票的概念归属（使用 data_gnzscfxx_ths 表，886代码体系）
        concept_stocks = defaultdict(lambda: {'codes': [], 'names': []})
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(
                "SELECT stock_code, index_code as concept_code FROM data_gnzscfxx_ths",
                conn
            ).to_dict('records')
        for row in rows:
            code = row['concept_code']
            name = concept_name_map.get(code, code)  # 使用886代码→名称映射
            concept_stocks[row['stock_code']]['codes'].append(code)
            concept_stocks[row['stock_code']]['names'].append(name)
        
        # 4. 加载债券映射
        bond_map = {}
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(
                "SELECT * FROM data_bond_ths",
                conn
            ).to_dict('records')
        for row in rows:
            # 使用第12列(正股代码2)作为标准股票代码
            values = list(row.values())
            stock_code = values[12]   # 第12列: 正股代码2 (标准股票代码)
            bond_code = values[1]     # 第1列: 债券代码
            bond_name = values[2]     # 第2列: 债券名称
            if stock_code:
                bond_map[stock_code] = {
                    'code': bond_code,
                    'name': bond_name
                }
        
        # 5. 获取股票名称映射
        stock_name_map = {}
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(
                "SELECT DISTINCT stock_code, short_name FROM data_industry_code_component_ths",
                conn
            ).to_dict('records')
        for row in rows:
            stock_name_map[row['stock_code']] = row['short_name']
        
        # 6. 合并写入宽表
        all_stocks = set(industry_stocks.keys()) | set(concept_stocks.keys())
        
        # 清空旧数据
        with mysql_tool.engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE cache_stock_industry_concept_bond"))
            conn.commit()
        
        # 批量插入
        insert_sql = """
            INSERT INTO cache_stock_industry_concept_bond 
            (stock_code, stock_name, industry_codes, industry_names, 
             concept_codes, concept_names, bond_code, bond_name, update_time)
            VALUES (:stock_code, :stock_name, :industry_codes, :industry_names,
                    :concept_codes, :concept_names, :bond_code, :bond_name, NOW())
        """
        
        batch = []
        for stock_code in all_stocks:
            industries = industry_stocks.get(stock_code, {'codes': [], 'names': []})
            concepts = concept_stocks.get(stock_code, {'codes': [], 'names': []})
            bond = bond_map.get(stock_code, {'code': None, 'name': None})
            
            batch.append({
                'stock_code': stock_code,
                'stock_name': stock_name_map.get(stock_code, ''),
                'industry_codes': json.dumps(industries['codes']),
                'industry_names': json.dumps(industries['names']),
                'concept_codes': json.dumps(concepts['codes']),
                'concept_names': json.dumps(concepts['names']),
                'bond_code': bond['code'],
                'bond_name': bond['name']
            })
            
            if len(batch) >= 500:
                with mysql_tool.engine.connect() as conn:
                    conn.execute(text(insert_sql), batch)
                    conn.commit()
                batch = []
        
        if batch:
            with mysql_tool.engine.connect() as conn:
                conn.execute(text(insert_sql), batch)
                conn.commit()
        
        logger.info(f"宽表缓存预热完成: {len(all_stocks)} 只股票")
        
        # 7. 加载到内存缓存
        load_memory_cache()
        
    except Exception as e:
        logger.error(f"宽表缓存预热失败: {e}")
        raise


def load_memory_cache():
    """加载宽表到内存缓存"""
    global _stock_cache, _bond_map
    
    logger.info("加载内存缓存...")
    
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql("SELECT * FROM cache_stock_industry_concept_bond", conn).to_dict('records')
        
        _stock_cache.clear()
        _bond_map.clear()
        
        for row in rows:
            stock_code = row['stock_code']
            
            industries = set(json.loads(row['industry_names'] or '[]'))
            concepts = set(json.loads(row['concept_names'] or '[]'))
            
            _stock_cache[stock_code] = {
                'stock_name': row['stock_name'],
                'industries': industries,
                'concepts': concepts,
                'bond_code': row['bond_code'],
                'bond_name': row['bond_name'],
            }
            
            if row['bond_code']:
                _bond_map[stock_code] = {
                    'code': row['bond_code'],
                    'name': row['bond_name']
                }
        
        logger.info(f"内存缓存加载完成: {len(_stock_cache)} 只股票")
        
    except Exception as e:
        logger.error(f"内存缓存加载失败: {e}")
        raise


def query_realtime_prices(stock_codes: List[str], date: str = None) -> Dict[str, dict]:
    """查询实时涨跌幅"""
    if not stock_codes:
        return {}
    
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        
        # 获取最新时间戳
        with mysql_tool.engine.connect() as conn:
            time_row = pd.read_sql(
                f"SELECT MAX(time) as max_time FROM monitor_gp_sssj_{date}",
                conn
            ).to_dict('records')
        
        if not time_row or not time_row[0]['max_time']:
            return {}
        
        max_time = time_row[0]['max_time']
        
        # 查询该时间点的数据
        placeholders = ','.join([f"'{code}'" for code in stock_codes])
        sql = f"""
            SELECT stock_code, short_name, price, change_pct 
            FROM monitor_gp_sssj_{date} 
            WHERE time = '{max_time}' AND stock_code IN ({placeholders})
        """
        
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(sql, conn).to_dict('records')
        
        result = {}
        for row in rows:
            result[row['stock_code']] = {
                'price': row['price'],
                'change_pct': float(row['change_pct']) if row['change_pct'] else 0,
                'short_name': row['short_name']
            }
        
        return result
        
    except Exception as e:
        logger.error(f"查询实时价格失败: {e}")
        return {}


def query_bond_realtime_prices(bond_codes: List[str], date: str = None) -> Dict[str, dict]:
    """查询转债实时涨跌幅"""
    if not bond_codes:
        return {}
    
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        table = f"monitor_zq_sssj_{date}"
        
        with mysql_tool.engine.connect() as conn:
            time_row = pd.read_sql(
                f"SELECT MAX(time) as max_time FROM {table}",
                conn
            ).to_dict('records')
        
        if not time_row or not time_row[0]['max_time']:
            return {}
        
        max_time = time_row[0]['max_time']
        placeholders = ','.join([f"'{code}'" for code in bond_codes])
        sql = f"""
            SELECT bond_code, price, change_pct 
            FROM {table}
            WHERE time = '{max_time}' AND bond_code IN ({placeholders})
        """
        
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(sql, conn).to_dict('records')
        
        return {row['bond_code']: {
            'price': row['price'],
            'change_pct': float(row['change_pct']) if row['change_pct'] else 0
        } for row in rows}
        
    except Exception as e:
        logger.error(f"查询转债实时价格失败: {e}")
        return {}


def query_cross_stocks(selected_tags: List[dict]) -> dict:
    """
    查询交叉选股结果
    """
    if not _stock_cache:
        load_memory_cache()
    
    # 构建选中标签集合
    selected_names = set(t['name'] for t in selected_tags)
    
    # 统计每只股票命中的标签
    stock_matches = {}
    
    for stock_code, data in _stock_cache.items():
        all_tags = data['industries'] | data['concepts']
        matched = selected_names & all_tags
        
        if matched:
            matched_industries = sorted([t for t in matched if t in data['industries']])
            matched_concepts = sorted([t for t in matched if t in data['concepts']])
            
            stock_matches[stock_code] = {
                'stock_name': data['stock_name'],
                'bond_code': data['bond_code'] or '-',
                'bond_name': data['bond_name'] or '-',
                'industries': matched_industries,
                'concepts': matched_concepts,
                'match_count': len(matched)
            }
    
    if not stock_matches:
        return {
            'tags': selected_tags,
            'groups': [],
            'summary': {
                'total_stocks': 0,
                'with_bond': 0,
                'query_time_ms': 0
            }
        }
    
    # 查询实时价格
    all_codes = list(stock_matches.keys())
    price_data = query_realtime_prices(all_codes)
    
    # 查询转债实时价格
    bond_codes = [m['bond_code'] for m in stock_matches.values() if m['bond_code'] != '-']
    bond_price_data = query_bond_realtime_prices(bond_codes)
    
    # 组装结果并分组
    groups = defaultdict(list)
    with_bond_count = 0
    
    for stock_code, match_info in stock_matches.items():
        price_info = price_data.get(stock_code, {})
        bond_info = bond_price_data.get(match_info['bond_code'], {})
        
        # 生成展示文本
        display_lines = match_info['industries'] + match_info['concepts']
        
        stock_result = {
            'stock_code': stock_code,
            'stock_name': match_info['stock_name'] or price_info.get('short_name', ''),
            'change_pct': price_info.get('change_pct', 0),
            'price': price_info.get('price', 0),
            'bond_code': match_info['bond_code'],
            'bond_name': match_info['bond_name'],
            'bond_change_pct': bond_info.get('change_pct', 0),
            'matched_industries': match_info['industries'],
            'matched_concepts': match_info['concepts'],
            'matched_tags_display': '\n'.join(display_lines)
        }
        
        groups[match_info['match_count']].append(stock_result)
        
        if match_info['bond_code'] != '-':
            with_bond_count += 1
    
    # 每组内按涨跌幅倒排
    result_groups = []
    for count in sorted(groups.keys(), reverse=True):
        stocks = groups[count]
        stocks.sort(key=lambda x: x['change_pct'], reverse=True)
        
        if count == len(selected_tags):
            label = f"命中全部 {count} 个"
        else:
            label = f"命中 {count} 个"
        
        result_groups.append({
            'match_count': count,
            'label': label,
            'stocks': stocks
        })
    
    return {
        'tags': selected_tags,
        'groups': result_groups,
        'summary': {
            'total_stocks': len(stock_matches),
            'with_bond': with_bond_count,
            'query_time_ms': 0
        }
    }


# 初始化
def init_service():
    """服务初始化"""
    init_pinyin_searcher()
    
    # 检查宽表是否存在数据
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            result = pd.read_sql(
                "SELECT COUNT(*) as c FROM cache_stock_industry_concept_bond",
                conn
            ).to_dict('records')
        
        if result and result[0]['c'] > 0:
            load_memory_cache()
        else:
            logger.info("宽表无数据，需要执行预热")
    except Exception as e:
        logger.error(f"检查宽表失败: {e}")
