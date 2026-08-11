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

from gs2026.utils import mysql_util, config_util, redis_util

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
    """查询实时涨跌幅（Redis优先）"""
    if not stock_codes:
        return {}

    if date is None:
        date = datetime.now().strftime('%Y%m%d')

    # 【优化】优先从Redis获取
    try:
        result = redis_util.get_realtime_prices_from_redis(date, stock_codes, 'stock')
        if result:
            logger.debug(f"从Redis获取实时价格: {len(result)} 只")
            return result
    except Exception as e:
        logger.warning(f"Redis获取价格失败: {e}")

    # 【回退】从MySQL获取
    try:
        mysql_tool = mysql_util.get_mysql_tool()

        # 【优化】使用Redis缓存的时间戳，避免子查询
        max_time = redis_util.get_max_time_from_redis(date, 'stock')

        with mysql_tool.engine.connect() as conn:
            if not max_time:
                # 如果Redis没有时间戳，查询MySQL
                time_row = pd.read_sql(
                    f"SELECT MAX(time) as max_time FROM monitor_gp_sssj_{date}",
                    conn
                ).to_dict('records')
                max_time = time_row[0]['max_time'] if time_row else None

            if not max_time:
                return {}

            placeholders = ','.join([f"'{code}'" for code in stock_codes])
            sql = f"""
                SELECT stock_code, short_name, price, change_pct
                FROM monitor_gp_sssj_{date}
                WHERE time = '{max_time}' AND stock_code IN ({placeholders})
            """

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
    """查询转债实时涨跌幅（Redis优先）"""
    if not bond_codes:
        return {}

    if date is None:
        date = datetime.now().strftime('%Y%m%d')

    # 【优化】优先从Redis获取
    try:
        result = redis_util.get_realtime_prices_from_redis(date, bond_codes, 'bond')
        if result:
            logger.debug(f"从Redis获取转债价格: {len(result)} 只")
            return result
    except Exception as e:
        logger.warning(f"Redis获取转债价格失败: {e}")

    # 【回退】从MySQL获取
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        table = f"monitor_zq_sssj_{date}"

        # 【优化】使用Redis缓存的时间戳
        max_time = redis_util.get_max_time_from_redis(date, 'bond')

        with mysql_tool.engine.connect() as conn:
            if not max_time:
                time_row = pd.read_sql(
                    f"SELECT MAX(time) as max_time FROM {table}",
                    conn
                ).to_dict('records')
                max_time = time_row[0]['max_time'] if time_row else None

            if not max_time:
                return {}

            placeholders = ','.join([f"'{code}'" for code in bond_codes])
            sql = f"""
                SELECT bond_code, price, change_pct
                FROM {table}
                WHERE time = '{max_time}' AND bond_code IN ({placeholders})
            """

            rows = pd.read_sql(sql, conn).to_dict('records')

        return {row['bond_code']: {
            'price': row['price'],
            'change_pct': float(row['change_pct']) if row['change_pct'] else 0
        } for row in rows}

    except Exception as e:
        logger.error(f"查询转债实时价格失败: {e}")
        return {}


def query_cross_stocks(selected_tags: List[dict], date: str = None) -> dict:
    """
    查询交叉选股结果
    
    Args:
        selected_tags: 选中的标签列表
        date: 日期(YYYYMMDD)，默认当天
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
    
    # 查询实时价格（传入日期）
    all_codes = list(stock_matches.keys())
    price_data = query_realtime_prices(all_codes, date)
    
    # 查询转债实时价格（传入日期）
    bond_codes = [m['bond_code'] for m in stock_matches.values() if m['bond_code'] != '-']
    bond_price_data = query_bond_realtime_prices(bond_codes, date)
    
    # 组装结果并分组
    groups = defaultdict(list)
    with_bond_count = 0
    
    for stock_code, match_info in stock_matches.items():
        price_info = price_data.get(stock_code, {})
        bond_info = bond_price_data.get(match_info['bond_code'], {})
        
        # 生成展示文本
        display_lines = match_info['industries'] + match_info['concepts']
        
        # 该股票本身的所有行业（与选中标签无关）
        stock_data = _stock_cache.get(stock_code, {})
        all_industries = sorted(list(stock_data.get('industries', set()))) if stock_data else []
        
        stock_result = {
            'stock_code': stock_code,
            'stock_name': match_info['stock_name'] or price_info.get('short_name', ''),
            'change_pct': price_info.get('change_pct', 0),
            'price': price_info.get('price', 0),
            'bond_code': match_info['bond_code'],
            'bond_name': match_info['bond_name'],
            'bond_change_pct': bond_info.get('change_pct', 0),
            'industry_name': '、'.join(all_industries) if all_industries else '',
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


def get_ztb_tags(date: str = None) -> dict:
    """
    获取涨停板的行业和概念标签
    
    数据源策略：
    - 当天日期：从 monitor_gp_sssj_{date} 表查 is_zt=1
    - 历史日期 或 当天无数据：从 analysis_ztb_detail_{year} 表查 trade_date
    
    然后通过股票代码查宽表获取完整行业和概念
    
    Args:
        date: 日期(YYYYMMDD)，默认当天
    
    Returns:
        {
            'date': '20260422',
            'total_zt': 78,
            'industries': [{'name': '半导体', 'type': 'industry', 'code': '881121', 'count': 8}, ...],
            'concepts': [{'name': 'AI应用', 'type': 'concept', 'code': '886055', 'count': 12}, ...]
        }
    """
    if not date:
        date = datetime.now().strftime('%Y%m%d')

    today = datetime.now().strftime('%Y%m%d')

    # 【优化1】优先从Redis获取涨停股票
    zt_codes = None
    if date == today:
        try:
            zt_codes = redis_util.get_zt_stocks_from_redis(date, 'stock')
            if zt_codes:
                logger.info(f"从Redis获取涨停股票: {len(zt_codes)} 只")
        except Exception as e:
            logger.warning(f"Redis查询失败，回退到MySQL: {e}")

    # 【优化2】Redis无数据，回退到MySQL
    if not zt_codes:
        mysql_tool = mysql_util.get_mysql_tool()

        if date == today:
            # 当天：从实时监控表查（只查最新时间点，避免全表扫描）
            try:
                with mysql_tool.engine.connect() as conn:
                    sql = (f"SELECT stock_code FROM monitor_gp_sssj_{date} "
                           f"WHERE is_zt = 1 AND `time` = "
                           f"(SELECT MAX(`time`) FROM monitor_gp_sssj_{date})")
                    rows = pd.read_sql(sql, conn).to_dict('records')
                    zt_codes = [r['stock_code'] for r in rows]
                    logger.info(f"从MySQL获取涨停股票: {len(zt_codes)} 只")
            except Exception as e:
                logger.warning(f"实时监控表查询失败({date}): {e}")

        if not zt_codes:
            # 历史日期：从涨停分析表查
            try:
                year = date[:4]
                table = f"analysis_ztb_detail_{year}"
                date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                with mysql_tool.engine.connect() as conn:
                    sql = f"SELECT DISTINCT stock_code FROM {table} WHERE trade_date = '{date_fmt}'"
                    rows = pd.read_sql(sql, conn).to_dict('records')
                    zt_codes = [r['stock_code'] for r in rows]
                    logger.info(f"从涨停分析表获取: {len(zt_codes)} 只")
            except Exception as e:
                logger.error(f"涨停分析表查询失败({date}): {e}")
    
    if not zt_codes:
        return {'date': date, 'total_zt': 0, 'industries': [], 'concepts': []}
    
    # 2. 从宽表内存缓存获取完整行业和概念
    if not _stock_cache:
        load_memory_cache()
    
    industry_counter = defaultdict(int)
    concept_counter = defaultdict(int)
    
    for code in zt_codes:
        stock_data = _stock_cache.get(code)
        if stock_data:
            for ind in stock_data['industries']:
                industry_counter[ind] += 1
            for con in stock_data['concepts']:
                concept_counter[con] += 1
    
    # 3. 构建名称→代码映射（从搜索器获取）
    searcher = init_pinyin_searcher()
    name_to_code = {}
    for item in searcher.items:
        name_to_code[item['name']] = item['code']
    
    # 4. 按频次降序排列，包含code
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
    
    logger.info(f"涨停标签统计: {len(zt_codes)}只涨停, {len(industries)}个行业, {len(concepts)}个概念")
    
    return {
        'date': date,
        'total_zt': len(zt_codes),
        'industries': industries,
        'concepts': concepts
    }


def _time_to_seconds(t) -> int:
    """把 TIME/timedelta/字符串 统一转成秒，无法解析返回 -1"""
    if t is None:
        return -1
    # pandas/SQLAlchemy 读出的 TIME 常为 timedelta
    if hasattr(t, 'total_seconds'):
        return int(t.total_seconds())
    s = str(t)
    try:
        parts = s.split(':')
        h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
        sec = int(float(parts[2])) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + sec
    except (ValueError, IndexError):
        return -1


def get_mainline_tags(date: str = None, time_str: str = None, top: int = 5) -> dict:
    """
    获取"主线前N"覆盖股票去重后的行业和概念标签
    
    数据源策略：
    - time_str 为空：取当天最终态主线（stock_anomaly_mainline），
      按 confidence DESC, stock_count DESC 取前 top 条
    - time_str 非空：盘中时点重建（stock_anomaly），过滤 anomaly_time<=T，
      按 mainline_names 聚合，用"截至该刻归属股票数"取前 top 条主线
    
    然后收集这些主线的所有股票代码去重，通过宽表内存缓存拿到行业/概念，
    按"被多少只主线股票命中"降序返回（决策C）。
    
    Args:
        date: 日期(YYYYMMDD)，默认当天
        time_str: 时间(HH:MM:SS)，可选，传入=盘中时点重建
        top: 主线数量，默认 5
    
    Returns:
        {
            'date': '20260810', 'time': None, 'top': 5,
            'mainlines': [{'name','stock_count','confidence'}],
            'stock_codes': [...],
            'industries': [{'name','type':'industry','code','count'}],
            'concepts':   [{'name','type':'concept','code','count'}]
        }
    """
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}"

    mysql_tool = mysql_util.get_mysql_tool()

    top_mainlines: List[dict] = []  # [{'name','stock_count','confidence','codes':set()}]

    if not time_str:
        # ===== 最终态：主线表 =====
        try:
            with mysql_tool.engine.connect() as conn:
                sql = text("""
                    SELECT mainline_name, confidence, stock_count, related_stocks
                    FROM stock_anomaly_mainline
                    WHERE trading_date = :d AND status = 'active'
                    ORDER BY confidence DESC, stock_count DESC
                    LIMIT :top
                """)
                rows = conn.execute(sql, {'d': date_fmt, 'top': int(top)}).fetchall()
            for r in rows:
                name, conf, cnt, rs = r[0], r[1], r[2], r[3]
                arr = json.loads(rs) if isinstance(rs, str) else (rs or [])
                codes = {x.get('code') for x in arr if x.get('code')}
                top_mainlines.append({
                    'name': name,
                    'confidence': int(conf) if conf is not None else None,
                    'stock_count': int(cnt) if cnt is not None else len(codes),
                    'codes': codes
                })
        except Exception as e:
            logger.error(f"主线表查询失败({date_fmt}): {e}")
    else:
        # ===== 盘中时点重建：stock_anomaly =====
        target_sec = _time_to_seconds(time_str)
        try:
            with mysql_tool.engine.connect() as conn:
                sql = text("""
                    SELECT anomaly_time, stock_code, mainline_names
                    FROM stock_anomaly
                    WHERE trading_date = :d AND ai_status = 'done'
                      AND mainline_names IS NOT NULL
                """)
                rows = conn.execute(sql, {'d': date_fmt}).fetchall()
            ml_codes = defaultdict(set)  # 主线名 -> set(股票)
            for at, code, ml in rows:
                if target_sec >= 0 and _time_to_seconds(at) > target_sec:
                    continue
                names = json.loads(ml) if isinstance(ml, str) else (ml or [])
                for nm in names:
                    if nm and nm not in ('无法归类', '独立个股'):
                        ml_codes[nm].add(code)
            ranked = sorted(ml_codes.items(), key=lambda kv: len(kv[1]), reverse=True)[:int(top)]
            for nm, codes in ranked:
                top_mainlines.append({
                    'name': nm,
                    'confidence': None,
                    'stock_count': len(codes),
                    'codes': set(codes)
                })
        except Exception as e:
            logger.error(f"盘中主线重建失败({date_fmt} {time_str}): {e}")

    # 收集所有主线股票去重
    all_codes = set()
    for m in top_mainlines:
        all_codes |= m['codes']

    if not all_codes:
        return {
            'date': date, 'time': time_str, 'top': int(top),
            'mainlines': [{'name': m['name'], 'stock_count': m['stock_count'],
                           'confidence': m['confidence']} for m in top_mainlines],
            'stock_codes': [], 'industries': [], 'concepts': []
        }

    # 股票 -> 行业/概念（复用内存缓存）
    if not _stock_cache:
        load_memory_cache()

    industry_counter = defaultdict(int)
    concept_counter = defaultdict(int)
    for code in all_codes:
        stock_data = _stock_cache.get(code)
        if stock_data:
            for ind in stock_data['industries']:
                industry_counter[ind] += 1
            for con in stock_data['concepts']:
                concept_counter[con] += 1

    # 名称 -> code（按 type 分离，避免行业/概念同名串码）
    searcher = init_pinyin_searcher()
    ind_name2code = {}
    con_name2code = {}
    for item in searcher.items:
        if item['type'] == 'industry':
            ind_name2code[item['name']] = item['code']
        else:
            con_name2code[item['name']] = item['code']

    industries = sorted(
        [{'name': n, 'type': 'industry', 'code': ind_name2code.get(n, ''), 'count': c}
         for n, c in industry_counter.items()],
        key=lambda x: x['count'], reverse=True
    )
    concepts = sorted(
        [{'name': n, 'type': 'concept', 'code': con_name2code.get(n, ''), 'count': c}
         for n, c in concept_counter.items()],
        key=lambda x: x['count'], reverse=True
    )

    logger.info(f"主线前{top}标签: 时点={time_str or '最终态'}, "
                f"{len(top_mainlines)}条主线, {len(all_codes)}只股票, "
                f"{len(industries)}个行业, {len(concepts)}个概念")

    return {
        'date': date,
        'time': time_str,
        'top': int(top),
        'mainlines': [{'name': m['name'], 'stock_count': m['stock_count'],
                       'confidence': m['confidence']} for m in top_mainlines],
        'stock_codes': sorted(all_codes),
        'industries': industries,
        'concepts': concepts
    }
