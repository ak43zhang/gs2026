"""

监控数据路由 - 支持股票、债券、行业三个排行榜

"""

from datetime import datetime

from typing import Dict, Optional

from flask import Blueprint, jsonify, request

import sys

from pathlib import Path

import pandas as pd

import time



# 添加项目根目录到路径

project_root = Path(__file__).parent.parent.parent.parent

if str(project_root) not in sys.path:

    sys.path.insert(0, str(project_root))



from gs2026.dashboard.services.data_service import DataService

from gs2026.utils.stock_bond_mapping_cache import get_cache



monitor_bp = Blueprint('monitor', __name__)

data_service = DataService()



# ==================== 【P0】单例数据库引擎 ====================

_shared_engine = None



def _get_shared_engine():

    """获取共享数据库引擎（避免每次请求创建新引擎）"""

    global _shared_engine

    if _shared_engine is None:

        from sqlalchemy import create_engine

        from ..config import Config

        _shared_engine = create_engine(Config.MYSQL_URI, pool_recycle=3600, pool_pre_ping=True)

    return _shared_engine



# ==================== 【P2】买点候选保存 ====================

def save_buy_point_candidates(date: str, time_str: str, candidates: list, market_data: dict):

    """保存买点候选到数据库（使用MD5去重）

    

    支持两种数据源：

    - 前端POST：candidate含level/tags字段，market_data含conditions数组

    - 后端计算：candidate含score/cond_*字段

    """

    if not candidates:

        return

    

    try:

        import json, hashlib

        from sqlalchemy import text

        

        engine = _get_shared_engine()

        

        save_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 and '-' not in date else date

        save_time = time_str or datetime.now().strftime('%H:%M:%S')

        

        sql = text("""

            INSERT INTO buy_point_candidates 

            (record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,

             bond_code, bond_price, bond_change_pct, level, star_color, condition_count, total_conditions,

             conditions, market_context)

            VALUES (:record_id, :date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,

             :bond_code, :bond_price, :bond_change_pct, :level, :star_color, :condition_count, :total_conditions,

             :conditions, :market_context)

            ON DUPLICATE KEY UPDATE

            stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),

            bond_price=VALUES(bond_price), bond_change_pct=VALUES(bond_change_pct),

            level=VALUES(level), star_color=VALUES(star_color), condition_count=VALUES(condition_count),

            conditions=VALUES(conditions), market_context=VALUES(market_context)

        """)

        

        market_ctx_json = json.dumps(market_data, ensure_ascii=False, default=str)

        

        with engine.connect() as conn:

            for c in candidates:

                try:

                    code = c.get('code', '')

                    record_id = hashlib.md5(f"{code}{save_date}{save_time}".encode()).hexdigest()

                    

                    # 优先使用前端传来的level，否则从score计算

                    level = c.get('level') or (3 if c.get('score', 0) >= 3 else (2 if c.get('score', 0) >= 2 else 1))

                    

                    # 条件信息：优先使用前端传来的tags

                    tags = c.get('tags', [])

                    if tags:

                        cond_list = [{'name': t, 'passed': True} for t in tags]

                    else:

                        cond_list = [

                            {'name': '主力净额/峰值', 'passed': bool(c.get('cond_net_ratio'))},

                            {'name': '行业排行', 'passed': bool(c.get('cond_industry'))},

                            {'name': '涨幅条件', 'passed': bool(c.get('cond_change_pct'))}

                        ]

                    condition_count = sum(1 for x in cond_list if x['passed'])

                    

                    conn.execute(sql, {

                        'record_id': record_id,

                        'date': save_date,

                        'time': save_time,

                        'stock_code': code,

                        'stock_name': c.get('name', ''),

                        'stock_price': c.get('price'),

                        'stock_change_pct': c.get('change_pct'),

                        'bond_code': c.get('bond_code') or '',

                        'bond_price': c.get('bond_price'),

                        'bond_change_pct': c.get('bond_chg'),

                        'level': level,

                        'star_color': c.get('starColor', 'yellow'),

                        'condition_count': condition_count,

                        'total_conditions': len(cond_list),

                        'conditions': json.dumps(cond_list, ensure_ascii=False),

                        'market_context': market_ctx_json

                    })

                except Exception as e3:

                    print(f"[保存单条失败] {c.get('code')}: {e3}")

            

            conn.commit()

    except Exception as e:

        print(f"[保存买点候选失败] {e}")


# ==================== 交易日判断 ====================
@monitor_bp.route('/latest-trading-date')
def get_latest_trading_date():
    """获取最近的交易日（如果今天不是交易日则返回上一个交易日）"""
    today = datetime.now().strftime('%Y-%m-%d')
    from sqlalchemy import text as sa_text
    sql = sa_text(
        "SELECT trade_date FROM data_jyrl "
        "WHERE trade_date <= :today AND trade_status = '1' "
        "ORDER BY trade_date DESC LIMIT 1"
    )
    try:
        engine = _get_shared_engine()
        with engine.connect() as conn:
            row = conn.execute(sql, {'today': today}).fetchone()
        trading_date = str(row[0]) if row else today
        is_today = (trading_date == today)
        return jsonify({'success': True, 'date': trading_date, 'is_today': is_today})
    except Exception as e:
        return jsonify({'success': True, 'date': today, 'is_today': True})


# ==================== 【P2】买点候选保存路由 ====================
@monitor_bp.route('/buy-points/save', methods=['POST'])
def save_buy_points():
    """保存买点候选（前端POST入口）"""
    try:
        data = request.get_json(silent=True) or {}
        date = data.get('date', '')
        time_str = data.get('time', '')
        candidates = data.get('candidates', [])
        market_context = data.get('market_context', {})
        
        if not date or not time_str:
            return jsonify(success=False, message='缺少日期或时间参数'), 400
        
        save_buy_point_candidates(date, time_str, candidates, market_context)
        return jsonify(success=True, message=f'已保存 {len(candidates)} 只')
    except Exception as e:
        print(f"[save_buy_points] {e}")
        import traceback; traceback.print_exc()
        return jsonify(success=False, message=str(e)), 500

# ==================== 【P1】DataFrame 进程级内存缓存 ====================

_df_cache = None

_df_cache_key = None



def get_cached_sssj_df(redis_key: str):

    """进程级缓存 DataFrame，同一 tick 内不重复加载"""

    global _df_cache, _df_cache_key

    if _df_cache_key == redis_key and _df_cache is not None:

        return _df_cache

    from gs2026.utils import redis_util

    df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)

    if df is not None and not df.empty:

        _df_cache = df

        _df_cache_key = redis_key

    return df





def _enrich_stock_data(stocks: list) -> list:

    """

    为股票数据添加债券、行业信息，以及绿名单标记（三层缓存策略优化版）



    Args:

        stocks: 原始股票数据列表



    Returns:

        添加债券/行业/绿名单标记后的股票数据列表

    """

    if not stocks:

        return stocks



    try:

        # 获取映射缓存

        cache = get_cache()



        # 【新增】获取绿名单缓存

        from gs2026.dashboard2.routes.green_bond_list_cache import get_green_bond_list

        green_bond_set = get_green_bond_list()  # 返回 Set[str]



        # 【优化】使用三层缓存策略获取映射

        stock_codes = [stock.get('code', '') for stock in stocks if stock.get('code')]

        mappings = cache.get_mappings_smart(stock_codes)



        # 填充数据

        for stock in stocks:

            stock_code = stock.get('code', '')

            mapping = mappings.get(stock_code)



            if mapping:

                bond_code = mapping.get('bond_code', '-')

                stock['bond_code'] = bond_code

                stock['bond_name'] = mapping.get('bond_name', '-')

                stock['industry_name'] = mapping.get('industry_name', '-')

                # 【新增】绿名单标记：债券代码存在且在绿名单集合中

                stock['is_green_bond'] = (

                    bond_code != '-' and

                    bond_code in green_bond_set

                )

            else:

                stock['bond_code'] = '-'

                stock['bond_name'] = '-'

                stock['industry_name'] = '-'

                stock['is_green_bond'] = False



        return stocks



    except Exception as e:

        print(f"[绿名单标记失败] {e}")

        # 出错时返回原始数据（带空字段），确保 is_green_bond 有默认值

        for stock in stocks:

            stock['bond_code'] = '-'

            stock['bond_name'] = '-'

            stock['industry_name'] = '-'

            stock['is_green_bond'] = False

        return stocks





def _is_historical(date: str | None) -> bool:

    """判断传入的日期是否为历史日期（非今天），历史日期需要走 MySQL"""

    if not date:

        return False

    today = datetime.now().strftime('%Y%m%d')

    return date != today


# ====== 增量排行优化（进程级缓存）======
_rank_incremental = {}       # { 'stock:20260706': { code: {'name':x, 'count':n} } }
_rank_last_time = {}         # { 'stock:20260706': '09:32:06' }


def _get_ranking_fast(asset_type, date, time_str, limit=0):
    """
    通用增量排行查询（stock/bond共用）

    路径1 - 时间前进（实时tick/滑动前进）:
        只查 time > last AND time <= current（~30行），内存累加
    路径2 - 时间后退 / 首次加载 / 宕机重启:
        共享引擎全量 GROUP BY 一次，重建计数器
    """
    from sqlalchemy import text

    engine = _get_shared_engine()
    prefix = 'gp' if asset_type == 'stock' else 'zq'
    table = f"monitor_{prefix}_top30_{date.replace('-', '')}"
    cache_key = f"{asset_type}:{date}"

    last_time = _rank_last_time.get(cache_key)
    counters = _rank_incremental.get(cache_key)

    if counters is not None and last_time and time_str > last_time:
        # ✅ 路径1: 时间前进 → 增量查询（~10ms）
        sql = text(f"SELECT code, name FROM {table} WHERE time > :last AND time <= :current")
        with engine.connect() as conn:
            rows = conn.execute(sql, {'last': last_time, 'current': time_str}).fetchall()
        for r in rows:
            code, name = r[0], r[1]
            if code in counters:
                counters[code]['count'] += 1
            else:
                counters[code] = {'name': name, 'count': 1}
    else:
        # ⚠️ 路径2: 后退/首次/重启 → 全量重建（~300ms）
        sql = text(f"""
            SELECT code, name, COUNT(*) as cnt FROM {table}
            WHERE time <= :time_str GROUP BY code, name
        """)
        with engine.connect() as conn:
            rows = conn.execute(sql, {'time_str': time_str}).fetchall()
        counters = {r[0]: {'name': r[1], 'count': r[2]} for r in rows}

    # 更新缓存
    _rank_incremental[cache_key] = counters
    _rank_last_time[cache_key] = time_str

    # 排序输出
    sorted_items = sorted(counters.items(), key=lambda x: -x[1]['count'])
    if limit:
        sorted_items = sorted_items[:limit]
    return [{'code': code, 'name': v['name'], 'count': v['count'], 'rank': i + 1}
            for i, (code, v) in enumerate(sorted_items)]


def _get_change_pct_batch(date: str, time_str: str, stock_codes: list) -> dict:

    """

    批量获取指定时间点的涨跌幅（从monitor_gp_sssj表）



    Args:

        date: 日期 YYYYMMDD

        time_str: 时间 HH:MM:SS

        stock_codes: 股票代码列表



    Returns:

        {stock_code: change_pct} 字典

    """

    if not stock_codes:

        return {}



    try:

        from gs2026.utils import redis_util



        # 1. 优先从Redis批量获取

        sssj_table = f"monitor_gp_sssj_{date}"

        redis_key = f"{sssj_table}:{time_str}"



        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)



        if df is not None and not df.empty:

            # 构建字典 {stock_code: change_pct}

            code_col = 'stock_code' if 'stock_code' in df.columns else 'code'

            change_col = 'change_pct'



            df[code_col] = df[code_col].astype(str).str.zfill(6)

            return df.set_index(code_col)[change_col].to_dict()



        # 2. Redis未命中，从MySQL查询

        return _get_change_pct_from_mysql(date, time_str, stock_codes)



    except Exception as e:

        print(f"批量获取涨跌幅失败: {e}")

        return {}





def _get_change_pct_from_mysql(date: str, time_str: str, stock_codes: list) -> dict:

    """从MySQL批量查询涨跌幅"""

    try:

        from sqlalchemy import create_engine, text

        from ..config import Config



        engine = create_engine(Config.MYSQL_URI)

        table_name = f"monitor_gp_sssj_{date}"



        # 批量查询（使用IN语句）

        codes_str = ','.join([f"'{code}'" for code in stock_codes])

        sql = text(f"""

            SELECT stock_code, change_pct

            FROM {table_name}

            WHERE time = :time_str AND stock_code IN ({codes_str})

        """)



        with engine.connect() as conn:

            df = pd.read_sql(sql, conn, params={'time_str': time_str})

            if not df.empty:

                df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)

                return df.set_index('stock_code')['change_pct'].to_dict()



        return {}



    except Exception as e:

        print(f"MySQL批量查询涨跌幅失败: {e}")

        return {}





def _get_bond_change_pct_batch(date: str, time_str: str, bond_codes: list) -> dict:

    """

    批量获取债券指定时间点的涨跌幅（从monitor_zq_sssj表）



    Args:

        date: 日期 YYYYMMDD

        time_str: 时间 HH:MM:SS

        bond_codes: 债券代码列表



    Returns:

        {bond_code: change_pct} 字典

    """

    if not bond_codes:

        return {}



    try:

        from gs2026.utils import redis_util



        # 1. 优先从Redis批量获取

        sssj_table = f"monitor_zq_sssj_{date}"

        redis_key = f"{sssj_table}:{time_str}"



        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)



        # Redis 无该时间点数据，直接从 MySQL 查询
        if df is None or df.empty:
            return _get_bond_change_pct_from_mysql(date, time_str, bond_codes)



        if df is not None and not df.empty:

            # 构建字典 {bond_code: change_pct}

            code_col = 'bond_code' if 'bond_code' in df.columns else 'code'

            change_col = 'change_pct'



            df[code_col] = df[code_col].astype(str)

            result = df.set_index(code_col)[change_col].to_dict()



            # 同时提取价格字段和金额字段

            if 'price' in df.columns:

                price_map = df.set_index(code_col)['price'].to_dict()

                amount_map = {}

                if 'amount' in df.columns:

                    amount_map = df.set_index(code_col)['amount'].to_dict()

                # 【新增】提取1分钟字段
                min1_pct_map = {}
                min1_amt_map = {}
                if 'min1_change_pct' in df.columns:
                    min1_pct_map = df.set_index(code_col)['min1_change_pct'].to_dict()
                if 'min1_amount' in df.columns:
                    min1_amt_map = df.set_index(code_col)['min1_amount'].to_dict()

                for code in result:

                    result[code] = {
                        'change_pct': result[code],
                        'price': price_map.get(code, '-'),
                        'amount': amount_map.get(code, 0),
                        'min1_change_pct': min1_pct_map.get(code),
                        'min1_amount': min1_amt_map.get(code),
                    }



            return result



        # 2. Redis未命中，从MySQL查询

        return _get_bond_change_pct_from_mysql(date, time_str, bond_codes)



    except Exception as e:

        print(f"批量获取债券涨跌幅失败: {e}")

        return {}





def _get_bond_change_pct_from_mysql(date: str, time_str: str, bond_codes: list) -> dict:

    """从MySQL批量查询债券涨跌幅和价格"""

    try:

        from sqlalchemy import create_engine, text

        from ..config import Config



        engine = create_engine(Config.MYSQL_URI)

        table_name = f"monitor_zq_sssj_{date}"



        # 批量查询（使用IN语句）

        codes_str = ','.join([f"'{code}'" for code in bond_codes])

        sql = text(f"""

            SELECT bond_code, change_pct, price, amount, min1_change_pct, min1_amount

            FROM {table_name}

            WHERE time = :time_str AND bond_code IN ({codes_str})

        """)



        with engine.connect() as conn:

            df = pd.read_sql(sql, conn, params={'time_str': time_str})

            if not df.empty:

                df['bond_code'] = df['bond_code'].astype(str)

                result = df.set_index('bond_code')['change_pct'].to_dict()

                # 同时提取价格和金额

                if 'price' in df.columns:

                    price_map = df.set_index('bond_code')['price'].to_dict()

                    amount_map = {}

                    if 'amount' in df.columns:

                        amount_map = df.set_index('bond_code')['amount'].to_dict()
                    min1_pct_map = df.set_index('bond_code')['min1_change_pct'].to_dict() if 'min1_change_pct' in df.columns else {}
                    min1_amt_map = df.set_index('bond_code')['min1_amount'].to_dict() if 'min1_amount' in df.columns else {}

                    for code in result:

                        result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-'), 'amount': amount_map.get(code, 0), 'min1_change_pct': min1_pct_map.get(code), 'min1_amount': min1_amt_map.get(code)}

                return result



        return {}



    except Exception as e:

        print(f"MySQL批量查询债券涨跌幅失败: {e}")

        return {}





def _get_bond_industry_batch(bond_codes: list) -> dict:

    """

    批量获取债券所属行业（优化版：使用 bond_industry 缓存，O(1)查询）



    Args:

        bond_codes: 债券代码列表



    Returns:

        {bond_code: industry_name} 字典

    """

    if not bond_codes:

        return {}



    try:

        # 优化后：使用 bond_industry 缓存直接查询（O(1)）

        from gs2026.dashboard2.cache.bond_industry import get_cache



        cache = get_cache()

        if not cache.ensure_cache():

            # 降级：返回默认值

            return {code: '-' for code in bond_codes}



        # O(1) 批量查询

        return cache.get_industries_batch(bond_codes)



    except Exception as e:

        print(f"批量获取债券行业失败: {e}")

        # 降级：返回默认值

        return {code: '-' for code in bond_codes}







def _get_bond_window_count_batch(date: str, time_str: str, bond_codes: list) -> dict:
    """
    批量获取债券的window_count（取截止时间的最新值）
    
    Args:
        date: 日期 YYYYMMDD
        time_str: 截止时间 HH:MM:SS
        bond_codes: 债券代码列表
    
    Returns:
        {bond_code: window_count} 字典
    """
    if not bond_codes or not time_str:
        return {}
    
    try:
        from sqlalchemy import create_engine, text
        from gs2026.utils import config_util
        
        url = config_util.get_config('common.url')
        engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
        table_name = f"monitor_zq_top30_{date}"
        
        # 批量查询：取每个债券截止时间的最新window_count
        codes_str = "','".join(bond_codes)
        sql = f"""
            SELECT t1.code, t1.window_count
            FROM {table_name} t1
            INNER JOIN (
                SELECT code, MAX(time) as max_time
                FROM {table_name}
                WHERE code IN ('{codes_str}') AND time <= '{time_str}'
                GROUP BY code
            ) t2 ON t1.code = t2.code AND t1.time = t2.max_time
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            return {row[0]: row[1] for row in result}
            
    except Exception as e:
        print(f"批量获取债券window_count失败: {e}")
        return {}

def _enrich_bond_data(bonds: list, date: str, time_str: str = None) -> list:

    """

    为债券数据添加涨跌幅和行业信息



    Args:

        bonds: 债券数据列表

        date: 日期 YYYYMMDD

        time_str: 时间 HH:MM:SS（可选）



    Returns:

        添加涨跌幅和行业信息后的债券数据列表

    """

    if not bonds:

        return bonds



    try:

        from gs2026.utils import redis_util

        client = redis_util._get_redis_client()



        # 确定查询时间

        if time_str:

            query_time = time_str

        else:

            # 获取最新时间戳

            sssj_table = f"monitor_zq_sssj_{date}"

            ts_key = f"{sssj_table}:timestamps"

            latest_ts = client.lindex(ts_key, 0)

            if latest_ts:

                query_time = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts

            else:

                # 无时间戳数据，全部设为"-"

                for bond in bonds:

                    bond['change_pct'] = '-'

                    bond['industry_name'] = '-'

                return bonds



        # 提取所有债券代码

        bond_codes = [b.get('code', '') for b in bonds if b.get('code')]



        # 批量获取涨跌幅和行业信息

        change_pct_map = _get_bond_change_pct_batch(date, query_time, bond_codes)

        industry_map = _get_bond_industry_batch(bond_codes)

        # 【新增】查询window_count（取截止时间的最新值）
        window_count_map = _get_bond_window_count_batch(date, query_time, bond_codes)



        # 填充数据

        for bond in bonds:

            code = bond.get('code', '')

            # 涨跌幅和价格（新格式是dict，旧格式是scalar）

            val = change_pct_map.get(code, '-')

            if isinstance(val, dict):

                bond['change_pct'] = val.get('change_pct', '-')

                bond['price'] = val.get('price', '-')

                bond['amount'] = float(val.get('amount', 0) or 0)

                bond['min1_change_pct'] = val.get('min1_change_pct')

                bond['min1_amount'] = val.get('min1_amount')

            else:

                bond['change_pct'] = val

                bond['price'] = '-'

                bond['amount'] = 0

            bond['industry_name'] = industry_map.get(code, '-')

            # 【新增】window_count
            bond['window_count'] = window_count_map.get(code, 0)



        return bonds



    except Exception as e:

        print(f"添加债券涨跌幅和行业信息失败: {e}")

        # 出错时全部设为"-"

        for bond in bonds:

            bond['change_pct'] = '-'

            bond['industry_name'] = '-'

        return bonds





def _enrich_change_pct(stocks: list, date: str, time_str: str = None) -> list:

    """

    为股票数据添加涨跌幅（批量优化版）

    从monitor_gp_sssj表批量获取指定时间的change_pct

    - 1次批量查询替代60次逐个查询

    - 只取指定时间点数据，不查找历史

    - 缺失数据保持"-"

    """

    if not stocks:

        return stocks



    try:

        from gs2026.utils import redis_util

        client = redis_util._get_redis_client()



        # 确定查询时间

        if time_str:

            query_time = time_str

        else:

            # 【修复】统一用 _get_latest_sssj_time（Redis优先，MySQL回退）

            query_time = _get_latest_sssj_time(date, 'stock')

            if not query_time:

                for stock in stocks:

                    stock['change_pct'] = '-'

                return stocks



        # 提取所有股票代码

        stock_codes = [s['code'].zfill(6) for s in stocks if s.get('code')]



        # 批量获取涨跌幅（1次查询）

        change_pct_map = _get_change_pct_batch(date, query_time, stock_codes)



        # 填充数据（无数据则保持"-"）

        for stock in stocks:

            code = stock.get('code', '').zfill(6)

            change_pct = change_pct_map.get(code)



            if change_pct is not None:

                stock['change_pct'] = change_pct

            else:

                stock['change_pct'] = '-'  # 停牌/新股等保持"-"



        return stocks



    except Exception as e:

        print(f"添加涨跌幅失败: {e}")

        # 出错时全部设为"-"

        for stock in stocks:

            stock['change_pct'] = '-'

        return stocks





def _enrich_change_pct_and_main_net(stocks: list, date: str, time_str: str = None) -> list:

    """

    为股票数据添加涨跌幅和主力净额（批量优化版）

    从 monitor_gp_sssj 表批量获取 change_pct 和累计 main_net_amount

    【替代原 _enrich_change_pct 函数】

    """

    if not stocks:

        return stocks



    try:

        from gs2026.utils import redis_util

        client = redis_util._get_redis_client()



        # 确定查询时间

        if time_str:

            query_time = time_str

        else:

            # 【修复】统一用 _get_latest_sssj_time（Redis优先，MySQL回退）

            query_time = _get_latest_sssj_time(date, 'stock')

            if not query_time:

                for stock in stocks:

                    stock['change_pct'] = '-'

                    stock['main_net_amount'] = 0

                return stocks



        # 提取所有股票代码

        stock_codes = [s['code'].zfill(6) for s in stocks if s.get('code')]



        # 批量获取涨跌幅和主力净额（1次查询，已包含累计值和派生字段）

        change_pct_map, main_net_map, derived_maps = _get_change_pct_and_main_net_batch(date, query_time, stock_codes)



        # 填充数据

        for stock in stocks:

            code = stock.get('code', '').zfill(6)



            # 涨跌幅（当前时间点）

            change_pct = change_pct_map.get(code)

            stock['change_pct'] = change_pct if change_pct is not None else '-'



            # 主力净额（已从cumulative_main_net或main_net_amount获取）

            main_net = main_net_map.get(code)

            stock['main_net_amount'] = main_net if main_net is not None else 0

            stock['cumulative_main_net'] = main_net if main_net is not None else 0  # 前端峰值净额计算需要



            # 派生字段（自动填充）

            for fname, fmap in derived_maps.items():

                stock[fname] = fmap.get(code, 0)



            # 价格字段

            if 'price' in derived_maps:

                stock['price'] = derived_maps['price'].get(code, '-')



        return stocks



    except Exception as e:

        print(f"添加涨跌幅和主力净额失败: {e}")

        for stock in stocks:

            stock['change_pct'] = '-'

            stock['main_net_amount'] = 0

        return stocks





def _get_change_pct_and_main_net_batch(date: str, time_str: str, stock_codes: list) -> tuple:

    """

    批量获取涨跌幅和主力净额和派生字段

    返回: (change_pct_map, main_net_map, derived_maps)

    """

    import pandas as pd

    from gs2026.utils import redis_util



    # 派生字段列表（与 monitor_derived_fields.py 同步）

    DERIVED_DISPLAY_FIELDS = ['consecutive_attacks', 'main_net_count', 'max_cumulative_main_net']



    if not stock_codes:

        return {}, {}, {f: {} for f in DERIVED_DISPLAY_FIELDS}



    change_pct_map = {}

    main_net_map = {}

    derived_maps = {f: {} for f in DERIVED_DISPLAY_FIELDS}



    def _extract_all_vectorized(df, code_col):

        """【性能优化】用向量化操作替代 iterrows，从 DataFrame 提取所有字段"""

        nonlocal change_pct_map, main_net_map, derived_maps



        # 确保 code 列已格式化

        codes = df[code_col].astype(str).str.zfill(6)



        # 涨跌幅（向量化）

        if 'change_pct' in df.columns:

            change_pct_map = dict(zip(codes, df['change_pct'].fillna(0).astype(float)))



        # 价格（向量化）

        if 'price' in df.columns:

            price_map = dict(zip(codes, df['price'].fillna(0).astype(float)))

            # 合并到 derived_maps 方便统一处理

            derived_maps['price'] = price_map



        # 主力净额（向量化，优先 cumulative_main_net）

        if 'cumulative_main_net' in df.columns:

            cum = df['cumulative_main_net'].fillna(0).astype(float)

            if 'main_net_amount' in df.columns:

                mna = df['main_net_amount'].fillna(0).astype(float)

                # cumulative_main_net 优先，为0时用 main_net_amount

                values = cum.where(cum != 0, mna)

            else:

                values = cum

            main_net_map = dict(zip(codes, values))

        elif 'main_net_amount' in df.columns:

            main_net_map = dict(zip(codes, df['main_net_amount'].fillna(0).astype(float)))



        # 派生字段（向量化）

        for fname in DERIVED_DISPLAY_FIELDS:

            if fname in df.columns:

                derived_maps[fname] = dict(zip(codes, df[fname].fillna(0).astype(float)))



    def _extract_derived(df, code_col):

        """从 DataFrame 提取派生字段（供 MySQL 路径使用）"""

        nonlocal derived_maps

        codes = df[code_col].astype(str).str.zfill(6)

        # 价格

        if 'price' in df.columns:

            derived_maps['price'] = dict(zip(codes, df['price'].fillna(0).astype(float)))

        # 其他派生字段

        for fname in DERIVED_DISPLAY_FIELDS:

            if fname in df.columns and fname != 'price':

                derived_maps[fname] = dict(zip(codes, df[fname].fillna(0).astype(float)))



    try:

        # 1. 【P1优化】优先从内存缓存获取 DataFrame

        sssj_table = f"monitor_gp_sssj_{date}"

        redis_key = f"{sssj_table}:{time_str}"



        df = get_cached_sssj_df(redis_key)



        if df is not None and not df.empty:

            code_col = 'stock_code' if 'stock_code' in df.columns else 'code'



            # 【性能优化】一次向量化操作提取所有字段（替代 3次 iterrows）

            _extract_all_vectorized(df, code_col)



            if change_pct_map and main_net_map:

                return change_pct_map, main_net_map, derived_maps

            # 如果Redis中没有主力净额字段，继续走MySQL查询



        # 2. Redis未命中或没有主力净额字段，从MySQL查询

        from sqlalchemy import text



        engine = _get_shared_engine()  # 【P0优化】使用单例引擎

        codes_str = ','.join([f"'{c}'" for c in stock_codes])

        table_name = f"monitor_gp_sssj_{date}"



        # 查询 cumulative_main_net + 派生字段 + price

        derived_cols = ', '.join(DERIVED_DISPLAY_FIELDS)

        query = f"""

            SELECT stock_code, change_pct, cumulative_main_net, {derived_cols}, price

            FROM {table_name}

            WHERE time = '{time_str}' AND stock_code IN ({codes_str})

        """



        with engine.connect() as conn:

            df = pd.read_sql(query, conn)

            # 【P1优化】用向量化替代 iterrows 循环
            if not df.empty:
                _extract_all_vectorized(df, 'stock_code')



    except Exception as e:

        print(f"批量查询涨跌幅和主力净额失败: {e}")



    return change_pct_map, main_net_map, derived_maps





@monitor_bp.route('/attack-ranking/stock', methods=['GET'])

def get_stock_ranking():

    """获取股票上攻排行（含债券/行业信息，支持实时和时间轴）"""

    try:

        date = request.args.get('date')

        time_str = request.args.get('time')  # 时间轴参数

        limit = int(request.args.get('limit', 0))  # 0=全量

        use_mysql = _is_historical(date)



        # 如果时间参数存在，使用 at-time 查询（时间轴模式）

        if time_str:

            actual_date = date or datetime.now().strftime('%Y%m%d')

            data = _get_ranking_fast('stock', actual_date, time_str, limit)

            # 补充债券和行业信息

            data = _enrich_stock_data(data)

            # 添加涨跌幅和主力净额（使用指定时间点）

            data = _enrich_change_pct_and_main_net(data, actual_date, time_str)

            # 标记红名单

            try:

                from gs2026.dashboard2.routes.red_list_cache import get_red_list

                red_list = get_red_list()

                for item in data:

                    item['is_red'] = item.get('code', '') in red_list

            except Exception:

                for item in data:

                    item['is_red'] = False

            # 排序：红名单优先，然后按次数倒序

            data.sort(key=lambda x: (-int(x.get('is_red', False)), -x.get('count', 0)))

            return jsonify({

                'success': True,

                'data': data,

                'count': len(data),

                'type': 'stock',

                'mode': 'timeline',

                'time': time_str

            })



        # 特殊处理1：历史日期（非今天）且未指定时间，自动使用15:00:00

        if date and _is_historical(date):

            data = _get_ranking_fast('stock', date, '15:00:00', limit)

            # 补充债券和行业信息

            data = _enrich_stock_data(data)

            # 添加涨跌幅和主力净额

            data = _enrich_change_pct_and_main_net(data, date, '15:00:00')

            # 标记红名单

            try:

                from gs2026.dashboard2.routes.red_list_cache import get_red_list

                red_list = get_red_list()

                for item in data:

                    item['is_red'] = item.get('code', '') in red_list

            except Exception:

                for item in data:

                    item['is_red'] = False

            # 排序：红名单优先，然后按次数倒序

            data.sort(key=lambda x: (-int(x.get('is_red', False)), -x.get('count', 0)))

            return jsonify({

                'success': True,

                'data': data,

                'count': len(data),

                'type': 'stock',

                'mode': 'historical',

                'note': '历史日期自动使用15:00:00数据'

            })



        # 特殊处理2：如果未指定时间且当前时间 > 15:00:00，自动使用15:00:00

        if not date:

            now = datetime.now().strftime('%H:%M:%S')

            if now > '15:00:00':

                date = datetime.now().strftime('%Y%m%d')

                data = _get_ranking_fast('stock', date, '15:00:00', limit)

                # 补充债券和行业信息

                data = _enrich_stock_data(data)

                # 添加涨跌幅和主力净额

                data = _enrich_change_pct_and_main_net(data, date, '15:00:00')

                # 标记红名单

                try:

                    from gs2026.dashboard2.routes.red_list_cache import get_red_list

                    red_list = get_red_list()

                    for item in data:

                        item['is_red'] = item.get('code', '') in red_list

                except Exception:

                    for item in data:

                        item['is_red'] = False

                # 排序：红名单优先，然后按次数倒序

                data.sort(key=lambda x: (-int(x.get('is_red', False)), -x.get('count', 0)))

                return jsonify({

                    'success': True,

                    'data': data,

                    'count': len(data),

                    'type': 'stock',

                    'note': '已自动回退到15:00:00数据'

                })



        # 获取原始股票数据（实时模式）

        data = data_service.get_stock_ranking(limit=limit, date=date, use_mysql=use_mysql)



        # 补充债券和行业信息

        data = _enrich_stock_data(data)



        # 添加涨跌幅和主力净额

        actual_date = date or datetime.now().strftime('%Y%m%d')

        data = _enrich_change_pct_and_main_net(data, actual_date)



        # 标记红名单

        try:

            from gs2026.dashboard2.routes.red_list_cache import get_red_list

            red_list = get_red_list()

            for item in data:

                item['is_red'] = item.get('code', '') in red_list

        except Exception:

            # 红名单标记失败不影响主功能

            for item in data:

                item['is_red'] = False



        # 排序：按次数倒序

        data.sort(key=lambda x: -x.get('count', 0))



        # 【修复】格式化价格为2位小数字符串，避免前端精度问题

        for item in data:

            price = item.get('price')

            if price is not None and price != '-':

                try:

                    item['price'] = f"{float(price):.2f}"

                except:

                    item['price'] = '-'



        return jsonify({

            'success': True,

            'data': data,

            'count': len(data),

            'type': 'stock',

            'mode': 'realtime'

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e),

            'type': 'stock'

        }), 500





@monitor_bp.route('/attack-ranking/bond', methods=['GET'])

def get_bond_ranking():

    """获取债券上攻排行（含涨跌幅、行业信息和绿名单标记）"""

    try:

        date = request.args.get('date')

        time_str = request.args.get('time')  # 时间参数，支持时间轴点击

        limit = int(request.args.get('limit', 0))  # 0=全量

        actual_date = date or datetime.now().strftime('%Y%m%d')

        # 如果时间参数存在，使用 at-time 查询（时间轴模式）
        if time_str:
            data = _get_ranking_fast('bond', actual_date, time_str, limit)
        elif date and _is_historical(date):
            # 历史日期且无time参数，自动使用15:00:00
            time_str = '15:00:00'
            data = _get_ranking_fast('bond', date, time_str, limit)
        else:
            # 当日实时模式
            use_mysql = True
            data = data_service.get_bond_ranking(limit=limit, date=date, use_mysql=use_mysql)

        # 添加涨跌幅和行业信息

        data = _enrich_bond_data(data, actual_date, time_str)



        # 标记绿名单（根据日期选择数据源：当天Redis/历史MySQL）

        try:

            from gs2026.dashboard2.routes.green_bond_list_cache import (

                get_green_bond_list, get_green_bond_list_cache_date

            )

            cache_date = get_green_bond_list_cache_date()

            if cache_date == actual_date:

                green_bond_list = get_green_bond_list()

            else:

                from gs2026.utils.mysql_util import get_mysql_tool

                mysql_tool = get_mysql_tool()

                date_sql = f"{actual_date[:4]}-{actual_date[4:6]}-{actual_date[6:8]}"

                df = pd.read_sql(

                    f"SELECT DISTINCT code FROM green_bond_list WHERE buy_date='{date_sql}'",

                    con=mysql_tool.engine

                )

                green_bond_list = set(df['code'].astype(str).str.zfill(6).tolist()) if not df.empty else set()

            for item in data:

                item['is_green'] = item.get('code', '') in green_bond_list

        except Exception as e:

            logger.warning(f"绿名单标记失败: {e}")

            for item in data:

                item['is_green'] = False



        # 【新增】标记3秒时间区间内的实时上攻数据并排序

        data = _mark_and_sort_realtime_attacks(data, actual_date, time_str)



        return jsonify({

            'success': True,

            'data': data,

            'count': len(data),

            'type': 'bond'

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e),

            'type': 'bond'

        }), 500





@monitor_bp.route('/attack-ranking/industry', methods=['GET'])

def get_industry_ranking():

    """获取行业上攻排行"""

    try:

        date = request.args.get('date')

        limit = int(request.args.get('limit', 30))

        use_mysql = True  # Redis优先，无数据自动回退MySQL（收盘后Redis过期场景）

        data = data_service.get_industry_ranking(limit=limit, date=date, use_mysql=use_mysql)

        return jsonify({

            'success': True,

            'data': data,

            'count': len(data),

            'type': 'industry'

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e),

            'type': 'industry'

        }), 500





@monitor_bp.route('/attack-ranking/all', methods=['GET'])

def get_all_rankings():

    """获取所有排行榜（股票、债券、行业）"""

    try:

        date = request.args.get('date')

        use_mysql = True  # Redis优先，无数据自动回退MySQL

        data = data_service.get_all_rankings(limit=30, date=date, use_mysql=use_mysql)

        return jsonify({

            'success': True,

            'data': data,

            'count': {

                'stock': len(data['stock']),

                'bond': len(data['bond']),

                'industry': len(data['industry'])

            }

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e)

        }), 500





@monitor_bp.route('/attack-ranking/<asset_type>/at-time', methods=['GET'])

def get_ranking_at_time(asset_type):

    """

    获取某个时间点的上攻排行



    Query Params:

        date: 日期 YYYYMMDD

        time: 截止时间 HH:MM:SS

        limit: 返回条数，默认0(全量)

    """

    try:

        date = request.args.get('date')

        time_str = request.args.get('time')

        limit = int(request.args.get('limit', 0))  # 0=全量

        data = data_service.get_ranking_at_time(

            asset_type=asset_type, limit=limit,

            date=date, time_str=time_str

        )



        # 【修复】为债券数据添加涨跌幅和行业信息

        if asset_type == 'bond' and data and time_str:

            actual_date = date or datetime.now().strftime('%Y%m%d')

            data = _enrich_bond_data(data, actual_date, time_str)



            # 【修复】标记绿名单（根据日期选择数据源：当天Redis/历史MySQL）

            try:

                from gs2026.dashboard2.routes.green_bond_list_cache import (

                    get_green_bond_list, get_green_bond_list_cache_date

                )

                cache_date = get_green_bond_list_cache_date()

                if cache_date == actual_date:

                    green_bond_list = get_green_bond_list()

                else:

                    from gs2026.utils.mysql_util import get_mysql_tool

                    mysql_tool = get_mysql_tool()

                    date_sql = f"{actual_date[:4]}-{actual_date[4:6]}-{actual_date[6:8]}"

                    df = pd.read_sql(

                        f"SELECT DISTINCT code FROM green_bond_list WHERE buy_date='{date_sql}'",

                        con=mysql_tool.engine

                    )

                    green_bond_list = set(df['code'].astype(str).str.zfill(6).tolist()) if not df.empty else set()

                for item in data:

                    item['is_green'] = item.get('code', '') in green_bond_list

            except Exception as e:

                logger.warning(f"at-time绿名单标记失败: {e}")

                for item in data:

                    item['is_green'] = False



        return jsonify({

            'success': True,

            'data': data,

            'count': len(data),

            'type': asset_type,

            'time': time_str

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e)

        }), 500





def _query_market_avg_fast(engine, date):
    """轻量查询大盘均值（复用共享引擎，无DataService实例化开销）"""
    from sqlalchemy import text
    table_name = f"monitor_gp_apqd_{date.replace('-', '')}"
    sql = text(f"SELECT time, avg_change_pct as change_pct FROM {table_name} ORDER BY time")
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [{'time': str(r[0]), 'change_pct': r[1]} for r in rows]
    except Exception as e:
        print(f'[market-overview] _query_market_avg_fast 失败: {e}')
        return []


def _query_bond_market_avg_fast(engine, date):
    """轻量查询债券大盘均值（复用共享引擎）"""
    from sqlalchemy import text
    table_name = f"monitor_zq_apqd_{date.replace('-', '')}"
    sql = text(f"SELECT time, avg_change_pct as change_pct FROM {table_name} ORDER BY time")
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [{'time': str(r[0]), 'change_pct': r[1]} for r in rows]
    except Exception as e:
        print(f'[market-overview] _query_bond_market_avg_fast 失败: {e}')
        return []


@monitor_bp.route('/market-overview', methods=['GET'])

def get_market_overview():

    """获取大盘数据"""

    try:

        date = request.args.get('date')

        time_str = request.args.get('time')

        use_mysql = True

        data = data_service.get_market_stats(date=date, use_mysql=use_mysql, time_str=time_str)

        # 补充查询：复用共享引擎，避免DataService实例化开销
        engine = _get_shared_engine()
        actual_date = date or datetime.now().strftime('%Y%m%d')

        if len(data.get('market_avg', [])) <= 1:
            data['market_avg'] = _query_market_avg_fast(engine, actual_date)

        if 'bond_market_avg' not in data or len(data.get('bond_market_avg', [])) <= 1:
            data['bond_market_avg'] = _query_bond_market_avg_fast(engine, actual_date)

        return jsonify({

            'success': True,

            'data': data

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e)

        }), 500





@monitor_bp.route('/timestamps', methods=['GET'])

def get_timestamps():

    """获取指定日期的所有数据时间点"""

    try:

        date = request.args.get('date')

        data = data_service.get_timestamps(date=date)

        return jsonify({

            'success': True,

            'data': data,

            'count': len(data)

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e)

        }), 500





@monitor_bp.route('/sector-distribution', methods=['GET'])

def get_sector_distribution():

    """获取板块分布数据"""

    try:

        date = request.args.get('date')

        use_mysql = True  # Redis优先，无数据自动回退MySQL

        data = data_service.get_industry_ranking(limit=30, date=date, use_mysql=use_mysql)

        return jsonify({

            'success': True,

            'data': data,

            'count': len(data)

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e)

        }), 500





@monitor_bp.route('/latest-messages', methods=['GET'])

def get_latest_messages():

    """获取最新消息（支持时间过滤）"""

    try:

        limit = 50

        date = request.args.get('date')

        time_str = request.args.get('time')  # 新增：时间过滤参数

        data = data_service.get_combine_ranking(limit=limit, date=date, time_str=time_str, check_change=request.args.get('check_change', '0') == '1')

        return jsonify({

            'success': True,

            'data': data,

            'count': len(data)

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e)

        }), 500





@monitor_bp.route('/chart-data/<bond_code>/<stock_code>', methods=['GET'])

def get_chart_data(bond_code, stock_code):

    """

    获取债券和正股的分时图数据



    Args:

        bond_code: 债券代码

        stock_code: 正股代码



    Query Params:

        date: 日期 YYYYMMDD，默认今天



    Returns:

        {

            'success': True,

            'data': {

                'bond': [{'time': '09:30:00', 'price': 120.5, 'change_pct': 0.5}, ...],

                'stock': [{'time': '09:30:00', 'price': 15.2, 'change_pct': 1.2}, ...]

            }

        }

    """

    try:

        date = request.args.get('date')

        data = data_service.get_chart_data(

            bond_code=bond_code,

            stock_code=stock_code,

            date=date

        )

        return jsonify({

            'success': True,

            'data': data

        })

    except Exception as e:

        return jsonify({

            'success': False,

            'error': str(e)

        }), 500





# ==================== 债券数据增强函数 ====================



# 【新增】时间查询缓存（5秒有效，避免重复查询）

_time_cache: Dict[str, tuple] = {}

_TIME_CACHE_TTL = 5  # 秒



def _get_cached_time(date: str, asset_type: str) -> Optional[str]:

    """获取缓存的时间（带TTL）"""

    key = f"{date}:{asset_type}"

    now = time.time()



    if key in _time_cache:

        cached_time, timestamp = _time_cache[key]

        if now - timestamp < _TIME_CACHE_TTL:

            return cached_time



    return None



def _set_cached_time(date: str, asset_type: str, time_str: str):

    """设置缓存的时间"""

    key = f"{date}:{asset_type}"

    _time_cache[key] = (time_str, time.time())





def _get_latest_sssj_time(date: str, asset_type: str = 'bond') -> str:

    """

    获取最新的实时数据时间，Redis优先，MySQL回退（带缓存优化）



    Args:

        date: 日期 YYYYMMDD

        asset_type: 'bond' 或 'stock'



    Returns:

        最新时间 HH:MM:SS，如果没有数据返回 None

    """

    # 【优化】先查缓存

    cached = _get_cached_time(date, asset_type)

    if cached:

        return cached



    try:

        from gs2026.utils import redis_util



        # 1. Redis timestamps list

        table_prefix = 'monitor_zq_sssj' if asset_type == 'bond' else 'monitor_gp_sssj'

        ts_key = f"{table_prefix}_{date}:timestamps"



        client = redis_util._get_redis_client()

        latest_ts = client.lindex(ts_key, 0)



        if latest_ts:

            result = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts

            _set_cached_time(date, asset_type, result)  # 【优化】缓存结果

            return result



        # 2. MySQL回退：收盘后Redis过期时从MySQL获取最后时间

        try:

            from sqlalchemy import text as sa_text

            engine = _get_shared_engine()  # 【P2优化】使用共享引擎

            table_name = f"{table_prefix}_{date}"

            with engine.connect() as conn:

                r = conn.execute(sa_text(f"SELECT MAX(`time`) FROM {table_name}"))

                row = r.fetchone()

                if row and row[0]:

                    result = str(row[0])

                    _set_cached_time(date, asset_type, result)  # 【优化】缓存结果

                    return result

        except Exception as e2:

            print(f"MySQL获取最新时间失败: {e2}")



        return None

    except Exception as e:

        print(f"获取最新实时数据时间失败: {e}")

        return None





def _get_bond_change_pct_from_mysql(date: str, time_str: str, bond_codes: list) -> dict:

    """从MySQL批量查询债券涨跌幅和价格"""

    try:

        from sqlalchemy import create_engine, text

        from ..config import Config



        engine = create_engine(Config.MYSQL_URI)

        table_name = f"monitor_zq_sssj_{date}"



        # 批量查询（使用IN语句）

        codes_str = ','.join([f"'{code}'" for code in bond_codes])

        sql = text(f"""

            SELECT bond_code, change_pct, price, amount, min1_change_pct, min1_amount

            FROM {table_name}

            WHERE time = :time_str AND bond_code IN ({codes_str})

        """)



        with engine.connect() as conn:

            df = pd.read_sql(sql, conn, params={'time_str': time_str})

            if not df.empty:

                df['bond_code'] = df['bond_code'].astype(str)

                result = df.set_index('bond_code')['change_pct'].to_dict()

                # 同时提取价格和金额

                if 'price' in df.columns:

                    price_map = df.set_index('bond_code')['price'].to_dict()

                    amount_map = {}

                    if 'amount' in df.columns:

                        amount_map = df.set_index('bond_code')['amount'].to_dict()
                    min1_pct_map = df.set_index('bond_code')['min1_change_pct'].to_dict() if 'min1_change_pct' in df.columns else {}
                    min1_amt_map = df.set_index('bond_code')['min1_amount'].to_dict() if 'min1_amount' in df.columns else {}

                    for code in result:

                        result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-'), 'amount': amount_map.get(code, 0), 'min1_change_pct': min1_pct_map.get(code), 'min1_amount': min1_amt_map.get(code)}

                return result



        return {}



    except Exception as e:

        print(f"MySQL批量查询债券涨跌幅失败: {e}")

        return {}







def _get_bond_window_count_batch(date: str, time_str: str, bond_codes: list) -> dict:
    """
    批量获取债券的window_count（取截止时间的最新值）
    
    Args:
        date: 日期 YYYYMMDD
        time_str: 截止时间 HH:MM:SS
        bond_codes: 债券代码列表
    
    Returns:
        {bond_code: window_count} 字典
    """
    if not bond_codes or not time_str:
        return {}
    
    try:
        from sqlalchemy import create_engine, text
        from gs2026.utils import config_util
        
        url = config_util.get_config('common.url')
        engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
        table_name = f"monitor_zq_top30_{date}"
        
        # 批量查询：取每个债券截止时间的最新window_count
        codes_str = "','".join(bond_codes)
        sql = f"""
            SELECT t1.code, t1.window_count
            FROM {table_name} t1
            INNER JOIN (
                SELECT code, MAX(time) as max_time
                FROM {table_name}
                WHERE code IN ('{codes_str}') AND time <= '{time_str}'
                GROUP BY code
            ) t2 ON t1.code = t2.code AND t1.time = t2.max_time
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            return {row[0]: row[1] for row in result}
            
    except Exception as e:
        print(f"批量获取债券window_count失败: {e}")
        return {}

def _enrich_bond_data(bonds: list, date: str, time_str: str = None) -> list:

    """

    为债券数据添加涨跌幅和行业信息



    Args:

        bonds: 债券数据列表

        date: 日期 YYYYMMDD

        time_str: 时间 HH:MM:SS（可选）



    Returns:

        添加涨跌幅和行业信息后的债券数据列表

    """

    if not bonds:

        return bonds



    try:

        from gs2026.utils import redis_util

        client = redis_util._get_redis_client()



        # 确定查询时间

        if time_str:

            query_time = time_str

        else:

            # 【修复】统一用 _get_latest_sssj_time（Redis优先，MySQL回退）

            query_time = _get_latest_sssj_time(date, 'bond')

            if not query_time:

                for bond in bonds:

                    bond['change_pct'] = '-'

                    bond['industry_name'] = '-'

                return bonds



        # 获取债券代码列表（确保字符串格式）

        bond_codes = [str(bond.get('code', '')) for bond in bonds]



        # 批量获取涨跌幅和行业信息

        import logging

        logging.warning(f"[DEBUG] 调用 _get_bond_change_pct_batch: date={date}, query_time={query_time}")

        change_pct_map = _get_bond_change_pct_batch(date, query_time, bond_codes)

        industry_map = _get_bond_industry_batch(bond_codes)

        logging.warning(f"[DEBUG] 涨跌幅字典大小: {len(change_pct_map)}")



        # 填充数据（代码转为字符串匹配）

        for bond in bonds:

            code = str(bond.get('code', ''))

            # 涨跌幅和价格（新格式是dict，旧格式是scalar）

            val = change_pct_map.get(code, '-')

            if isinstance(val, dict):

                bond['change_pct'] = val.get('change_pct', '-')

                # 格式化价格为2位小数

                price_val = val.get('price', '-')

                if price_val != '-' and price_val is not None:

                    try:

                        bond['price'] = f"{float(price_val):.2f}"

                    except:

                        bond['price'] = '-'

                else:

                    bond['price'] = '-'

                bond['amount'] = float(val.get('amount', 0) or 0)

                bond['min1_change_pct'] = val.get('min1_change_pct')

                bond['min1_amount'] = val.get('min1_amount')

            else:

                bond['change_pct'] = val

                bond['price'] = '-'

                bond['amount'] = 0

            bond['industry_name'] = industry_map.get(code, '-')

            logging.warning(f"[DEBUG] 代码 {code}: change_pct={bond['change_pct']}")



        return bonds



    except Exception as e:

        import traceback

        print(f"[ERROR] 增强债券数据失败: {e}")

        traceback.print_exc()

        # 返回原始数据（带空字段）

        for bond in bonds:

            bond['change_pct'] = '-'

            bond['industry_name'] = '-'

        return bonds





def _mark_and_sort_realtime_attacks(bonds: list, date: str, time_str: str = None) -> list:

    """

    标记3秒时间区间内的实时上攻数据并排序



    排序逻辑：

    1. 3秒时间区间内的实时上攻数据优先（带"实"标记）

    2. 实时数据内部按上攻次数降序

    3. 非实时数据按上攻次数降序



    Args:

        bonds: 债券数据列表

        date: 日期 YYYYMMDD

        time_str: 时间 HH:MM:SS（可选）



    Returns:

        标记并排序后的债券数据列表

    """

    if not bonds:

        return bonds



    try:

        from gs2026.utils import redis_util

        from datetime import datetime, timedelta

        from gs2026.utils.mysql_util import MysqlTool

        import pandas as pd



        client = redis_util._get_redis_client()



        # 确定查询时间

        if time_str:

            query_time = time_str

        else:

            # 【修复】Redis优先，MySQL回退

            query_time = _get_latest_sssj_time(date, 'bond')

            if not query_time:

                for bond in bonds:

                    bond['is_realtime'] = False

                return sorted(bonds, key=lambda x: x.get('count', 0), reverse=True)



        # 解析查询时间为datetime

        query_dt = datetime.strptime(f"{date} {query_time}", "%Y%m%d %H:%M:%S")



        # 计算3秒时间区间（当前时间往前推3秒）

        start_time = (query_dt - timedelta(seconds=3)).strftime("%H:%M:%S")

        end_time = query_time



        # 【修复】从MySQL top30表查询3秒区间内的债券

        realtime_codes = set()



        try:

            # 构建表名

            table_name = f"monitor_zq_top30_{date}"



            # 查询3秒区间内的债券代码

            query = f"""

                SELECT DISTINCT code

                FROM {table_name}

                WHERE time >= '{start_time}' AND time <= '{end_time}'

            """



            mysql_tool = MysqlTool()

            with mysql_tool.engine.connect() as conn:

                df = pd.read_sql(query, conn)

                if not df.empty:

                    realtime_codes = set(df['code'].astype(str).tolist())

                    print(f"[DEBUG] 3秒区间({start_time}-{end_time})内实时上攻债券: {len(realtime_codes)} 个")



        except Exception as e:

            print(f"[DEBUG] 查询实时上攻数据失败: {e}")



        # 标记实时数据

        for bond in bonds:

            code = str(bond.get('code', ''))

            is_realtime = code in realtime_codes

            bond['is_realtime'] = is_realtime





        # 【修改】默认排序不再减去 tick 上涨，仅按上攻次数降序

        # tick 上涨通过背景色标记，不再优先排序

        bonds.sort(key=lambda x: -x.get('count', 0))



        return bonds



    except Exception as e:

        import traceback

        print(f"[ERROR] 标记实时上攻数据失败: {e}")

        traceback.print_exc()

        # 返回原始数据，全部标记为非实时

        for bond in bonds:

            bond['is_realtime'] = False

        return sorted(bonds, key=lambda x: x.get('count', 0), reverse=True)





@monitor_bp.route('/buy-points', methods=['GET'])



def _time_to_seconds(t):

    """时间/timedelta转秒数"""

    if t is None:

        return 0

    if hasattr(t, 'total_seconds'):

        return int(t.total_seconds())

    s = str(t)

    parts = s.split(':')

    if len(parts) == 3:

        return int(parts[0])*3600 + int(parts[1])*60 + int(float(parts[2]))

    return 0



def _find_nearest_price(prices, signal_time, offset_min):

    """在sssj价格序列中找 signal_time + offset_min 最近的价格"""

    sig_sec = _time_to_seconds(signal_time)

    target_sec = sig_sec + offset_min * 60

    # 午休调整: 11:30(41400) ~ 13:00(46800)

    if 41400 < target_sec < 46800:

        target_sec = 46800 + (target_sec - 41400)

    best_price = None

    best_diff = 999999

    for ts, price in prices:

        diff = abs(ts - target_sec)

        if diff < best_diff and diff < 300:

            best_diff = diff

            best_price = price

    return best_price



def _find_close_price(prices):

    """取最后一条价格作为收盘价"""

    if not prices:

        return None

    return prices[-1][1]


def _find_peak_price(prices, signal_time):
    """找到信号时间之后的最高价格"""
    sig_sec = _time_to_seconds(signal_time)
    peak = None
    for sec, price in prices:
        if sec > sig_sec:
            if peak is None or price > peak:
                peak = price
    return peak


# 【修复】改为返回涨跌幅而非价格
def _find_nearest_change_pct(prices, signal_time, offset_min):
    """在sssj价格序列中找 signal_time + offset_min 最近的涨跌幅"""
    sig_sec = _time_to_seconds(signal_time)
    target_sec = sig_sec + offset_min * 60
    # 午休调整: 11:30(41400) ~ 13:00(46800)
    if 41400 < target_sec < 46800:
        target_sec = 46800 + (target_sec - 41400)
    best_change_pct = None
    best_diff = 999999
    for ts, price, change_pct in prices:
        diff = abs(ts - target_sec)
        if diff < best_diff and diff < 300:
            best_diff = diff
            best_change_pct = change_pct
    return best_change_pct


def _find_close_change_pct(prices):
    """取最后一条的涨跌幅作为收盘涨跌幅"""
    if not prices:
        return None
    # 返回最后一条的 change_pct
    return prices[-1][2] if len(prices[-1]) > 2 else None





@monitor_bp.route('/buy-points/generate-effects', methods=['POST'])

def generate_effects():

    """为指定日期的买点候选填充效果追踪数据（股票+债券）"""

    from sqlalchemy import text

    try:

        data = request.get_json(silent=True) or {}

        target_date = data.get('date', '')

        # 支持星级筛选

        levels = data.get('levels', [1, 2, 3])

        if not isinstance(levels, list):

            levels = [1, 2, 3]

        # 修复：如果levels为空，返回空结果
        if not levels:
            return jsonify(success=True, filled=0, skipped=0, details=[], stats={})

        if not target_date:

            return jsonify(success=False, message='缺少date参数'), 400



        if '-' in target_date:

            save_date = target_date

            date_compact = target_date.replace('-', '')

        else:

            date_compact = target_date

            save_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"



        engine = _get_shared_engine()

        filled = 0

        skipped = 0

        details = []



        # 自动检测并添加效果追踪字段（股票+债券）

        _ensure_effect_columns(engine)



        with engine.connect() as conn:

            # 1. 获取该日期所有买点候选（支持星级筛选）

            level_placeholders = ','.join([str(l) for l in levels])

            candidates = conn.execute(text(f"""

                SELECT record_id, stock_code, stock_name, stock_price, time, level,

                       bond_code, bond_price, stock_change_pct, bond_change_pct, star_color

                FROM buy_point_candidates WHERE date = :d AND level IN ({level_placeholders})

                ORDER BY time ASC

            """), {'d': save_date}).fetchall()



            if not candidates:

                return jsonify(success=True, filled=0, skipped=0, details=[], stats={})



            # 2. 提取所有股票代码和债券代码

            stock_codes = list(set(str(c[1]) for c in candidates if c[1]))

            bond_codes = list(set(str(c[6]) for c in candidates if c[6] and str(c[6]) != '-'))



            # 3. 批量获取股票分时价格（从 monitor_gp_sssj_{date}）

            stock_sssj = _batch_get_sssj_prices(conn, f"monitor_gp_sssj_{date_compact}", stock_codes, 'stock_code')



            # 4. 批量获取债券分时价格（从 monitor_zq_sssj_{date}）

            bond_sssj = _batch_get_sssj_prices(conn, f"monitor_zq_sssj_{date_compact}", bond_codes, 'bond_code')



            # 5. 逐条计算效果

            for c in candidates:

                record_id = c[0]

                stock_code = str(c[1])

                stock_name = c[2]

                stock_signal_price = float(c[3]) if c[3] else None

                signal_time = c[4]

                level = c[5]

                bond_code = str(c[6]) if c[6] else '-'

                bond_signal_price = float(c[7]) if c[7] else None

                # 命中涨跌幅（信号出现时的涨跌幅）

                signal_change_pct = float(c[8]) if c[8] is not None else None

                bond_signal_change_pct = float(c[9]) if c[9] is not None else None

                star_color = c[10] or 'yellow'



                # --- 股票效果 ---

                s5, s15, s30, sc, s_peak = None, None, None, None, None

                sp5, sp15, sp30, spc, sp_peak = None, None, None, None, None

                if stock_signal_price and stock_signal_price > 0 and signal_change_pct is not None:

                    stock_prices = stock_sssj.get(stock_code, [])

                    if not stock_prices:

                        print(f"[DEBUG] No sssj data for stock {stock_code} on {date_compact}")

                    else:

                        # 【修复】计算昨日收盘价，然后用价格计算绝对涨跌幅

                        # 昨日收盘价 = 信号价格 / (1 + 信号涨跌幅/100)

                        pre_close = stock_signal_price / (1 + signal_change_pct / 100)

                        

                        sp5 = _find_nearest_price(stock_prices, signal_time, 5)

                        sp15 = _find_nearest_price(stock_prices, signal_time, 15)

                        sp30 = _find_nearest_price(stock_prices, signal_time, 30)

                        spc = _find_close_price(stock_prices)

                        sp_peak = _find_peak_price(stock_prices, signal_time)

                        

                        # 计算绝对涨跌幅: (价格 - 昨日收盘) / 昨日收盘 * 100

                        def calc_abs_change(p):

                            return round((p - pre_close) / pre_close * 100, 4) if p else None

                        

                        s5 = calc_abs_change(sp5)

                        s15 = calc_abs_change(sp15)

                        s30 = calc_abs_change(sp30)

                        sc = calc_abs_change(spc)

                        s_peak = calc_abs_change(sp_peak)

                        print(f"[DEBUG] Stock {stock_code} at {signal_time}: pre_close={pre_close:.2f}, s5={s5}, s15={s15}, s30={s30}, sc={sc}")



                # --- 债券效果 ---

                b5, b15, b30, bc, b_peak = None, None, None, None, None

                bp5, bp15, bp30, bpc, bp_peak = None, None, None, None, None

                if bond_code != '-' and bond_signal_price and bond_signal_price > 0 and bond_signal_change_pct is not None:

                    bond_prices = bond_sssj.get(bond_code, [])

                    if bond_prices:

                        # 【修复】计算昨日收盘价，然后用价格计算绝对涨跌幅

                        bond_pre_close = bond_signal_price / (1 + bond_signal_change_pct / 100)

                        

                        bp5 = _find_nearest_price(bond_prices, signal_time, 5)

                        bp15 = _find_nearest_price(bond_prices, signal_time, 15)

                        bp30 = _find_nearest_price(bond_prices, signal_time, 30)

                        bpc = _find_close_price(bond_prices)

                        bp_peak = _find_peak_price(bond_prices, signal_time)

                        

                        def calc_bond_abs_change(p):

                            return round((p - bond_pre_close) / bond_pre_close * 100, 4) if p else None

                        

                        b5 = calc_bond_abs_change(bp5)

                        b15 = calc_bond_abs_change(bp15)

                        b30 = calc_bond_abs_change(bp30)

                        bc = calc_bond_abs_change(bpc)

                        b_peak = calc_bond_abs_change(bp_peak)



                # 有任一效果数据才算filled

                if any(v is not None for v in [s5, s15, s30, sc, s_peak, b5, b15, b30, bc, b_peak]):

                    conn.execute(text("""

                        UPDATE buy_point_candidates SET

                            after_5m_price=:sp5, after_5m_change_pct=:s5,

                            after_15m_price=:sp15, after_15m_change_pct=:s15,

                            after_30m_price=:sp30, after_30m_change_pct=:s30,

                            after_close_price=:spc, after_close_change_pct=:sc,

                            after_peak_price=:sp_peak, after_peak_change_pct=:s_peak,

                            bond_after_5m_price=:bp5, bond_after_5m_change_pct=:b5,

                            bond_after_15m_price=:bp15, bond_after_15m_change_pct=:b15,

                            bond_after_30m_price=:bp30, bond_after_30m_change_pct=:b30,

                            bond_after_close_price=:bpc, bond_after_close_change_pct=:bc,

                            bond_after_peak_price=:bp_peak, bond_after_peak_change_pct=:b_peak

                        WHERE record_id=:rid

                    """), {'sp5':sp5,'s5':s5,'sp15':sp15,'s15':s15,

                           'sp30':sp30,'s30':s30,'spc':spc,'sc':sc,

                           'sp_peak':sp_peak,'s_peak':s_peak,

                           'bp5':bp5,'b5':b5,'bp15':bp15,'b15':b15,

                           'bp30':bp30,'b30':b30,'bpc':bpc,'bc':bc,

                           'bp_peak':bp_peak,'b_peak':b_peak,

                           'rid':record_id})

                    filled += 1

                else:

                    skipped += 1



                details.append({

                    'time': str(signal_time), 'code': stock_code, 'name': stock_name,

                    'bond_code': bond_code, 'level': level, 'star_color': star_color,

                    'stock_signal_price': stock_signal_price,

                    'stock_signal_change_pct': signal_change_pct,  # 命中涨跌幅

                    'stock_5m': s5, 'stock_15m': s15, 'stock_30m': s30, 'stock_close': sc, 'stock_peak': s_peak,

                    'bond_signal_price': bond_signal_price,

                    'bond_signal_change_pct': bond_signal_change_pct,  # 债券命中涨跌幅

                    'bond_5m': b5, 'bond_15m': b15, 'bond_30m': b30, 'bond_close': bc, 'bond_peak': b_peak

                })



            conn.commit()



        # 6. 分段统计（股票+债券分别统计）

        stats = {

            'stock': _calc_effect_stats(details, 'stock_'),

            'bond': _calc_effect_stats(details, 'bond_')

        }



        return jsonify(success=True, filled=filled, skipped=skipped,

                       details=details, stats=stats)

    except Exception as e:

        print(f"[generate-effects] {e}")

        import traceback; traceback.print_exc()

        return jsonify(success=False, message=str(e)), 500



def _batch_get_sssj_prices(conn, table_name: str, codes: list, code_column: str) -> dict:
    """批量从sssj表获取价格序列，返回 {code: [(seconds, price), ...]}"""
    from sqlalchemy import text
    result = {}
    if not codes:
        return result
    try:
        placeholders = ','.join([f"'{c}'" for c in codes])
        rows = conn.execute(text(f"""
            SELECT {code_column}, time, price FROM {table_name}
            WHERE {code_column} IN ({placeholders})
            ORDER BY {code_column}, time
        """)).fetchall()
        for row in rows:
            result.setdefault(str(row[0]), []).append(
                (_time_to_seconds(row[1]), float(row[2]))
            )
    except Exception as e:
        print(f"[EFFECT] 查询{table_name}失败: {e}")
    return result



def _calc_effect_stats(details: list, prefix: str) -> dict:

    """计算分段统计（prefix='stock_'或'bond_'）"""

    stats = {}

    for period, suffix in [('5m', '5m'), ('15m', '15m'), ('30m', '30m'), ('close', 'close'), ('peak', 'peak')]:

        key = f'{prefix}{suffix}'

        valid = [d[key] for d in details if d.get(key) is not None]

        stats[period] = {

            'total': len(valid),

            'success': sum(1 for v in valid if v > 0),

            'success_rate': round(sum(1 for v in valid if v > 0) / len(valid) * 100, 1) if valid else 0,

            'avg_return': round(sum(valid) / len(valid), 4) if valid else 0

        }

    return stats



def _ensure_effect_columns(engine):

    """自动检测并添加效果追踪字段（股票+债券共16个字段）"""

    from sqlalchemy import text

    all_columns = [

        # 股票效果字段

        ('after_5m_price', 'DECIMAL(10,2)'),

        ('after_5m_change_pct', 'DECIMAL(6,4)'),

        ('after_15m_price', 'DECIMAL(10,2)'),

        ('after_15m_change_pct', 'DECIMAL(6,4)'),

        ('after_30m_price', 'DECIMAL(10,2)'),

        ('after_30m_change_pct', 'DECIMAL(6,4)'),

        ('after_close_price', 'DECIMAL(10,2)'),

        ('after_close_change_pct', 'DECIMAL(6,4)'),
        ('after_peak_price', 'DECIMAL(10,3)'),
        ('after_peak_change_pct', 'DECIMAL(6,4)'),

        # 债券效果字段

        ('bond_after_5m_price', 'DECIMAL(10,3)'),

        ('bond_after_5m_change_pct', 'DECIMAL(6,4)'),

        ('bond_after_15m_price', 'DECIMAL(10,3)'),

        ('bond_after_15m_change_pct', 'DECIMAL(6,4)'),

        ('bond_after_30m_price', 'DECIMAL(10,3)'),

        ('bond_after_30m_change_pct', 'DECIMAL(6,4)'),

        ('bond_after_close_price', 'DECIMAL(10,3)'),

        ('bond_after_close_change_pct', 'DECIMAL(6,4)'),
        ('bond_after_peak_price', 'DECIMAL(10,3)'),
        ('bond_after_peak_change_pct', 'DECIMAL(6,4)'),

    ]

    try:

        with engine.connect() as conn:

            for col_name, col_type in all_columns:

                exists = conn.execute(text("""

                    SELECT COUNT(*) FROM information_schema.COLUMNS

                    WHERE TABLE_NAME = 'buy_point_candidates'

                    AND COLUMN_NAME = :col

                """), {'col': col_name}).scalar()

                if exists == 0:

                    print(f"[EFFECT] 添加字段: {col_name} {col_type}")

                    conn.execute(text(f"ALTER TABLE buy_point_candidates ADD COLUMN {col_name} {col_type} DEFAULT NULL"))

            conn.commit()

    except Exception as e:

        print(f"[EFFECT] 检测/添加字段失败: {e}")



        return jsonify(success=False, message=str(e)), 500



@monitor_bp.route('/buy-points/recent', methods=['GET'])
def get_recent_buy_points():
    """获取近期买点候选（去重：每只股票只取最新一条，附带命中次数）"""
    from sqlalchemy import text
    try:
        date = request.args.get('date', '')
        limit = int(request.args.get('limit', '20'))
        before = request.args.get('before', '')
        if limit > 50: limit = 50

        save_date = date if '-' in date else (f'{date[:4]}-{date[4:6]}-{date[6:8]}' if len(date) == 8 else '')
        if not save_date:
            now = datetime.now()
            save_date = f'{now.year}-{now.month:02d}-{now.day:02d}'

        engine = _get_shared_engine()

        with engine.connect() as conn:
            # 构建WHERE条件
            where_clause = "date = :d"
            params = {'d': save_date, 'l': limit}
            if before:
                where_clause += " AND time <= :before"
                params['before'] = before

            # 查询：每只股票最新一条 + 命中次数（仅2星及以上）
            sql = f"""
                WITH latest AS (
                    SELECT stock_code, stock_name, stock_price, stock_change_pct,
                           bond_code, bond_price, bond_change_pct,
                           level, time, condition_count, total_conditions, conditions, star_color,
                           ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY time DESC) as rn
                    FROM buy_point_candidates
                    WHERE {where_clause} AND level >= 2
                ),
                counts AS (
                    SELECT stock_code, COUNT(*) as hit_count
                    FROM buy_point_candidates
                    WHERE {where_clause} AND level >= 2
                    GROUP BY stock_code
                )
                SELECT l.*, c.hit_count
                FROM latest l
                JOIN counts c ON l.stock_code = c.stock_code
                WHERE l.rn = 1
                ORDER BY l.time DESC
                LIMIT :l
            """

            result = conn.execute(text(sql), params)
            rows = result.fetchall()

            if not rows:
                return jsonify(success=True, items=[])

            # 组装返回数据
            items = []
            for row in rows:
                items.append({
                    'stock_code': row[0],
                    'stock_name': row[1],
                    'stock_price': float(row[2]) if row[2] else None,
                    'stock_change_pct': float(row[3]) if row[3] else 0,
                    'bond_code': row[4] or '',
                    'bond_price': float(row[5]) if row[5] else None,
                    'bond_change_pct': float(row[6]) if row[6] else 0,
                    'level': row[7] or 1,
                    'time': str(row[8]) if row[8] else '',
                    'condition_count': row[9] or 0,
                    'total_conditions': row[10] or 0,
                    'conditions': row[11] or '[]',
                    'star_color': row[12] or 'yellow',
                    'hit_count': row[14] or 1
                })

            return jsonify(success=True, items=items)

    except Exception as e:
        print(f"[get_recent_buy_points] {e}")
        import traceback; traceback.print_exc()
        return jsonify(success=False, message=str(e)), 500

def get_recent_buy_points():

    from sqlalchemy import text

    try:

        date = request.args.get('date', '')

        limit = int(request.args.get('limit', '3'))

        before = request.args.get('before', '')

        if limit > 10: limit = 10

        save_date = date if '-' in date else (f'{date[:4]}-{date[4:6]}-{date[6:8]}' if len(date) == 8 else '')

        if not save_date:

            now = datetime.now()

            save_date = f'{now.year}-{now.month:02d}-{now.day:02d}'



        engine = _get_shared_engine()

        groups = []



        with engine.connect() as conn:

            if before:

                result = conn.execute(

                    text("SELECT DISTINCT time FROM buy_point_candidates WHERE date = :d AND time <= :before ORDER BY time DESC LIMIT :l"),

                    {'d': save_date, 'before': before, 'l': limit}

                )

            else:

                result = conn.execute(

                    text("SELECT DISTINCT time FROM buy_point_candidates WHERE date = :d ORDER BY time DESC LIMIT :l"),

                    {'d': save_date, 'l': limit}

                )

            times = [str(row[0]) for row in result]

            if not times:

                return jsonify(success=True, groups=[])



            ts = ','.join([f"'{t}'" for t in times])

            result = conn.execute(

                text(f"SELECT time,stock_code,stock_name,stock_price,stock_change_pct,bond_code,bond_price,bond_change_pct,level,star_color,condition_count,total_conditions,conditions FROM buy_point_candidates WHERE date = :d AND time IN ({ts}) ORDER BY time DESC, level DESC, stock_code"),

                {'d': save_date}

            )



            time_map = {}

            for row in result:

                t = str(row[0])

                if t not in time_map:

                    time_map[t] = []

                time_map[t].append({

                    'stock_code': row[1], 'stock_name': row[2],

                    'stock_price': float(row[3]) if row[3] else None,

                    'stock_change_pct': float(row[4]) if row[4] else None,

                    'bond_code': row[5] or '',

                    'bond_price': float(row[6]) if row[6] else None,

                    'bond_change_pct': float(row[7]) if row[7] else None,

                    'level': row[8], 'star_color': row[9] or 'yellow',

                    'condition_count': row[10],

                    'total_conditions': row[11], 'conditions': row[12]

                })



            for t in times:

                if t in time_map:

                    groups.append({'time': t, 'items': time_map[t]})



        return jsonify(success=True, groups=groups)

    except Exception as e:

        print(f'[buy-points/recent] {e}')

        return jsonify(success=False, message=str(e)), 500



# ==================== 【买点候选回溯】 ====================

@monitor_bp.route('/buy-points/backtest/query-timepoints', methods=['POST'])
def query_backtest_timepoints():
    """查询日期范围内每天的时间点数量"""
    try:
        from gs2026.dashboard2.routes.backtest_worker import task_manager
        data = request.get_json(silent=True) or {}
        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')
        if not start_date or not end_date:
            return jsonify(success=False, message='缺少日期参数'), 400

        result = task_manager.query_timepoints(start_date, end_date)
        result['success'] = True
        return jsonify(result)
    except Exception as e:
        print(f'[backtest/query-timepoints] {e}')
        return jsonify(success=False, message=str(e)), 500


@monitor_bp.route('/buy-points/backtest', methods=['POST'])
def start_backtest():
    """启动买点候选回溯任务"""
    try:
        from gs2026.dashboard2.routes.backtest_worker import task_manager
        data = request.get_json(silent=True) or {}
        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')
        conditions = data.get('conditions', {})

        if not start_date or not end_date:
            return jsonify(success=False, message='缺少日期参数'), 400
        if not conditions:
            return jsonify(success=False, message='缺少条件参数'), 400

        task_id = task_manager.submit(start_date, end_date, conditions)
        task = task_manager.get_status(task_id)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f'回溯任务已启动',
            'total_points': task.total_points if task else 0
        })
    except Exception as e:
        print(f'[backtest/start] {e}')
        return jsonify(success=False, message=str(e)), 500


@monitor_bp.route('/buy-points/backtest/status', methods=['GET'])
def get_backtest_status():
    """获取回溯任务状态"""
    try:
        from gs2026.dashboard2.routes.backtest_worker import task_manager
        task_id = request.args.get('task_id', '')
        if not task_id:
            return jsonify(success=False, message='缺少task_id'), 400

        task = task_manager.get_status(task_id)
        if not task:
            return jsonify(success=False, message='任务不存在'), 404

        return jsonify({
            'success': True,
            'task_id': task.task_id,
            'status': task.status,
            'progress': round(task.progress, 4),
            'current_date': task.current_date,
            'current_time': task.current_time,
            'processed': task.processed_points,
            'total': task.total_points,
            'status_detail': getattr(task, 'status_detail', ''),
            'error': task.error,
            'result': {
                'total_candidates': task.total_candidates,
                'completed_at': task.completed_at
            } if task.status == 'completed' else None
        })
    except Exception as e:
        print(f'[backtest/status] {e}')
        return jsonify(success=False, message=str(e)), 500


# ==================== 【买点条件配置 API】 ====================
import json
import os

_BP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'bp_conditions.json')
_BP_CONFIG_CACHE = None

def _load_bp_config():
    """加载买点条件配置"""
    global _BP_CONFIG_CACHE
    if _BP_CONFIG_CACHE is not None:
        return _BP_CONFIG_CACHE
    try:
        with open(_BP_CONFIG_PATH, 'r', encoding='utf-8') as f:
            _BP_CONFIG_CACHE = json.load(f)
        return _BP_CONFIG_CACHE
    except Exception as e:
        print(f"[MONITOR] 加载条件配置失败: {e}")
        return {'conditions': []}

@monitor_bp.route('/api/bp_conditions', methods=['GET'])
def get_bp_conditions():
    """获取买点条件配置（供前端加载）"""
    config = _load_bp_config()
    return jsonify(config)


# ====== 债券量化回测 ======

# ====== 实时量化选债 ======

def _get_current_sssj(date=None, time=None):
    """获取指定时间点的全量sssj数据（共享引擎直查MySQL）
    
    Args:
        date: 日期 YYYYMMDD
        time: 时间点 HHMMSS，为None时取最新
    """
    from sqlalchemy import text as sa_text
    engine = _get_shared_engine()
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    table = f"monitor_zq_sssj_{date}"
    try:
        with engine.connect() as conn:
            if time:
                # 获取指定时间点数据
                df = pd.read_sql(
                    sa_text(f"SELECT * FROM {table} WHERE time = :t"),
                    conn, params={'t': time}
                )
            else:
                # 获取最新时间点
                row = conn.execute(sa_text(f"SELECT MAX(time) FROM {table}")).fetchone()
                if not row or not row[0]:
                    return None
                latest_time = str(row[0])
                df = pd.read_sql(
                    sa_text(f"SELECT * FROM {table} WHERE time = :t"),
                    conn, params={'t': latest_time}
                )
        return df
    except Exception as e:
        print(f"[quant-screen] _get_current_sssj error: {e}")
        return None


@monitor_bp.route('/quant-screen', methods=['POST'])
def quant_screen():
    """实时量化选债：对当前tick数据应用MySQL中勾选的方案(is_active=1)"""
    import pandas as pd
    from sqlalchemy import text
    
    # 从请求获取日期
    data = request.get_json() or {}
    
    # 从MySQL加载在用方案(is_active=1且use_realtime=1)
    try:
        engine = _get_shared_engine()
        sql = text("""
            SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct, 
                   max_hold_time, price_offset, offset_mode
            FROM quant_screen_schemes 
            WHERE is_active = 1 AND use_realtime = 1
        """)
        with engine.connect() as conn:
            result = conn.execute(sql)
            schemes = []
            for row in result:
                import json
                schemes.append({
                    'name': row.scheme_name,
                    'conditions': json.loads(row.conditions_json) if row.conditions_json else [],
                    'stop_loss': float(row.stop_loss_pct) if row.stop_loss_pct else 3.0,
                    'take_profit': float(row.take_profit_pct) if row.take_profit_pct else 5.0,
                    'max_hold_time': row.max_hold_time,
                    'price_offset': float(row.price_offset) if row.price_offset else 0.0,
                    'offset_mode': row.offset_mode or 'fixed'
                })
    except Exception as e:
        print(f"[quant-screen] 加载方案失败: {e}")
        return jsonify({'success': False, 'error': f'加载方案失败: {e}'}), 500
    
    if not schemes:
        return jsonify({'success': True, 'matches': [], 'stats': {}, 'time': '', 'schemes': [], 'message': '没有在用方案'})

    # 获取指定时间点的tick数据（支持时间轴回放）
    date = data.get('date') or datetime.now().strftime('%Y%m%d')
    time = data.get('time')  # 可选：时间点 HHMMSS，为空则取最新
    df = _get_current_sssj(date, time)
    if df is None or df.empty:
        return jsonify({'success': True, 'matches': [], 'stats': {}, 'time': time or ''})

    current_time = str(df['time'].iloc[0]) if 'time' in df.columns else (time or '')

    # 对每个方案应用条件
    matches = []
    stats = {}
    seen = {}  # bond_code → {scheme_names}

    for scheme in schemes:
        name = scheme.get('name', '')
        conditions = scheme.get('conditions', [])
        if not conditions:
            stats[name] = 0
            continue

        mask = pd.Series(True, index=df.index)
        for c in conditions:
            field = c.get('field', '')
            if field not in df.columns:
                continue
            op = c.get('op', '>')
            val = float(c.get('value', 0))
            if op == '>':      mask &= df[field] > val
            elif op == '>=':   mask &= df[field] >= val
            elif op == '<':    mask &= df[field] < val
            elif op == '<=':   mask &= df[field] <= val
            elif op == '=':    mask &= df[field] == val
            elif op == '!=':   mask &= df[field] != val
            elif op == 'between':
                val2 = float(c.get('value2', val))
                mask &= (df[field] >= val) & (df[field] <= val2)

        hit = df[mask]
        stats[name] = len(hit)

        for _, row in hit.iterrows():
            code = row.get('bond_code', '')
            if code in seen:
                # 合并方案名
                for m in matches:
                    if m['bond_code'] == code:
                        m['scheme_names'].append(name)
                        break
            else:
                seen[code] = True
                matches.append({
                    'scheme_names': [name],
                    'bond_code': code,
                    'bond_name': row.get('bond_name', ''),
                    'price': round(float(row.get('price', 0)), 3),
                    'change_pct': round(float(row.get('change_pct', 0)), 2),
                    'amount': int(row.get('amount', 0)),
                    'amount_rank': int(row.get('amount_rank', 0)) if pd.notna(row.get('amount_rank')) else 0,
                    'slope_short': round(float(row.get('slope_short', 0)), 6) if pd.notna(row.get('slope_short')) else 0,
                    'min1_change_pct': round(float(row.get('min1_change_pct', 0)), 4) if pd.notna(row.get('min1_change_pct')) else 0,
                })

    # 按涨幅降序排列
    matches.sort(key=lambda x: -x['change_pct'])
    
    # 保存命中记录到数据库
    try:
        _save_quant_screen_hits(date, current_time, matches, schemes, df)
    except Exception as e:
        print(f"[quant-screen] 保存命中记录失败: {e}")
        # 不影响返回结果

    return jsonify({
        'success': True,
        'time': current_time,
        'matches': matches,
        'stats': stats,
        'schemes': schemes,  # 返回使用的方案供前端显示
    })


def _save_quant_screen_hits(trade_date, tick_time, matches, schemes, df):
    """保存量化选债命中记录到数据库"""
    from sqlalchemy import text
    
    if not matches:
        return
    
    # 转换tick_time格式: "10:16:57" -> "101657"
    if ':' in str(tick_time):
        tick_time = tick_time.replace(':', '')
    
    engine = _get_shared_engine()
    
    # 构建方案参数字典
    scheme_params = {}
    for scheme in schemes:
        name = scheme.get('name', '')
        scheme_params[name] = {
            'stop_loss_pct': scheme.get('stop_loss', 0),
            'take_profit_pct': scheme.get('take_profit', 0),
            'max_hold_time': scheme.get('max_hold_time'),
            'price_offset': scheme.get('price_offset', 0.0),
            'offset_mode': scheme.get('offset_mode', 'fixed'),
        }
    
    # 获取当前tick数据用于查找完整信息
    tick_data = {}
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            code = row.get('bond_code', '')
            if code:
                tick_data[code] = row
    
    with engine.connect() as conn:
        for match in matches:
            bond_code = match.get('bond_code', '')
            scheme_names = match.get('scheme_names', [])
            
            for scheme_name in scheme_names:
                params = scheme_params.get(scheme_name, {})
                
                # 获取该债券在当前tick的数据
                row = tick_data.get(bond_code, {})
                signal_price = match.get('price', 0)
                
                # 应用价格偏移计算实际入场价
                price_offset = params.get('price_offset', 0.0)
                offset_mode = params.get('offset_mode', 'fixed')
                if offset_mode == 'percent':
                    entry_price = signal_price * (1 + price_offset / 100)
                else:
                    entry_price = signal_price + price_offset
                
                # 计算止损止盈价格（基于实际入场价）
                stop_loss_pct = params.get('stop_loss_pct', 0)
                take_profit_pct = params.get('take_profit_pct', 0)
                stop_loss_price = entry_price * (1 - stop_loss_pct / 100) if stop_loss_pct else None
                take_profit_price = entry_price * (1 + take_profit_pct / 100) if take_profit_pct else None
                
                sql = text("""
                    INSERT INTO quant_screen_hits (
                        trade_date, tick_time, scheme_name, bond_code, bond_name,
                        entry_price, entry_change_pct, entry_amount,
                        stop_loss_pct, take_profit_pct, stop_loss_price, take_profit_price, max_hold_time,
                        current_price, current_return_pct, signal_status,
                        is_locked
                    ) VALUES (
                        :trade_date, :tick_time, :scheme_name, :bond_code, :bond_name,
                        :entry_price, :entry_change_pct, :entry_amount,
                        :stop_loss_pct, :take_profit_pct, :stop_loss_price, :take_profit_price, :max_hold_time,
                        :current_price, :current_return_pct, :signal_status,
                        :is_locked
                    )
                    ON DUPLICATE KEY UPDATE
                        current_price = VALUES(current_price),
                        current_return_pct = VALUES(current_return_pct),
                        updated_at = CURRENT_TIMESTAMP
                """)
                
                conn.execute(sql, {
                    'trade_date': trade_date,
                    'tick_time': tick_time,
                    'scheme_name': scheme_name,
                    'bond_code': bond_code,
                    'bond_name': match.get('bond_name', ''),
                    'entry_price': entry_price,
                    'entry_change_pct': match.get('change_pct', 0),
                    'entry_amount': match.get('amount', 0),
                    'stop_loss_pct': stop_loss_pct,
                    'take_profit_pct': take_profit_pct,
                    'stop_loss_price': stop_loss_price,
                    'take_profit_price': take_profit_price,
                    'max_hold_time': params.get('max_hold_time'),
                    'current_price': entry_price,
                    'current_return_pct': 0,
                    'signal_status': 'entry',
                    'is_locked': 0
                })
        
        conn.commit()
        print(f"[quant-screen] 保存了 {len(matches)} 条命中记录")


@monitor_bp.route('/quant-screen/hits', methods=['GET'])
def get_quant_screen_hits():
    """查询量化选债历史命中记录"""
    from sqlalchemy import text
    
    date = request.args.get('date', datetime.now().strftime('%Y%m%d'))
    scheme = request.args.get('scheme')  # 可选：筛选特定方案
    limit = request.args.get('limit', 100, type=int)
    after_id = request.args.get('after_id', type=int)  # 增量刷新：只返回id > after_id的记录
    
    try:
        engine = _get_shared_engine()
        
        # 构建查询条件
        where_clauses = ['trade_date = :date']
        params = {'date': date, 'limit': limit}
        
        if scheme:
            where_clauses.append('scheme_name = :scheme')
            params['scheme'] = scheme
        
        if after_id:
            where_clauses.append('id > :after_id')
            params['after_id'] = after_id
        
        sql = text(f"""
            SELECT * FROM quant_screen_hits 
            WHERE {' AND '.join(where_clauses)}
            ORDER BY id DESC
            LIMIT :limit
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
        
        if df.empty:
            return jsonify({'success': True, 'hits': [], 'count': 0, 'last_id': after_id or 0})
        
        # 替换NaN为None，避免JSON序列化错误
        df = df.replace({float('nan'): None, float('inf'): None, float('-inf'): None})
        
        # 转换数据
        hits = df.to_dict('records')
        
        # 格式化时间
        for hit in hits:
            if 'tick_time' in hit:
                hit['tick_time'] = str(hit['tick_time'])
            if 'created_at' in hit:
                hit['created_at'] = str(hit['created_at'])
            if 'locked_at' in hit and hit['locked_at']:
                hit['locked_at'] = str(hit['locked_at'])
        
        # 获取最新id
        last_id = max([h.get('id', 0) for h in hits]) if hits else (after_id or 0)
        
        return jsonify({
            'success': True,
            'hits': hits,
            'count': len(hits),
            'date': date,
            'last_id': last_id
        })
        
    except Exception as e:
        print(f"[quant-screen/hits] 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@monitor_bp.route('/backtest/bond/fields', methods=['GET'])
def get_backtest_bond_fields():
    """获取回测可用字段列表"""
    from gs2026.dashboard2.services.backtest_bond import BACKTEST_FIELDS
    return jsonify({'success': True, 'fields': BACKTEST_FIELDS})


@monitor_bp.route('/backtest/bond', methods=['POST'])
def run_backtest_bond():
    """执行债券量化回测"""
    from gs2026.dashboard2.services.backtest_bond import run_bond_backtest
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求体为空'}), 400

        engine = _get_shared_engine()

        summary, trades = run_bond_backtest(
            engine=engine,
            date=data.get('date', ''),
            conditions=data.get('conditions', []),
            tp_pct=float(data.get('take_profit_pct', 0.5)),
            sl_pct=float(data.get('stop_loss_pct', 0.3)),
            window_minutes=int(data.get('window_minutes', 5)),
            dedup=data.get('dedup', 'first_per_minute'),
            time_start=data.get('time_start', '09:30:00'),
            time_end=data.get('time_end', '15:00:00'),
            price_offset=float(data.get('price_offset', 0.0)),
            offset_mode=data.get('offset_mode', 'fixed'),
            return_calc_method=data.get('return_calc_method', 'compound'),
        )

        return jsonify({'success': True, 'summary': summary, 'trades': trades})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 量化选债方案管理API ====================

@monitor_bp.route('/quant-schemes', methods=['GET'])
def get_quant_schemes():
    """获取方案列表"""
    from sqlalchemy import text
    
    active_only = request.args.get('active_only', '0') == '1'
    scene = request.args.get('scene')  # backtest, realtime, replay
    
    try:
        engine = _get_shared_engine()
        
        # 构建查询
        where_clauses = ['1=1']
        params = {}
        
        if active_only:
            where_clauses.append('is_active = 1')
        
        if scene:
            scene_map = {
                'backtest': 'use_backtest',
                'realtime': 'use_realtime',
                'replay': 'use_replay'
            }
            if scene in scene_map:
                where_clauses.append(f'{scene_map[scene]} = 1')
        
        sql = text(f"""
            SELECT id, scheme_name, scheme_desc, conditions_json,
                   stop_loss_pct, take_profit_pct, max_hold_time,
                   price_offset, offset_mode, time_start, time_end,
                   is_active, use_backtest, use_realtime, use_replay,
                   created_at, updated_at
            FROM quant_screen_schemes
            WHERE {' AND '.join(where_clauses)}
            ORDER BY updated_at DESC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
        
        if df.empty:
            return jsonify({'success': True, 'schemes': []})
        
        # 转换数据
        schemes = []
        for _, row in df.iterrows():
            try:
                conditions = json.loads(row['conditions_json']) if row['conditions_json'] else []
            except:
                conditions = []
            
            schemes.append({
                'id': int(row['id']),
                'scheme_name': row['scheme_name'],
                'scheme_desc': row['scheme_desc'] or '',
                'conditions': conditions,
                'stop_loss_pct': float(row['stop_loss_pct']) if pd.notna(row['stop_loss_pct']) else 3.0,
                'take_profit_pct': float(row['take_profit_pct']) if pd.notna(row['take_profit_pct']) else 5.0,
                'max_hold_time': int(row['max_hold_time']) if pd.notna(row['max_hold_time']) else 30,
                'price_offset': float(row['price_offset']) if pd.notna(row['price_offset']) else 0.0,
                'offset_mode': row['offset_mode'] or 'fixed',
                'time_start': row['time_start'] or '09:30',
                'time_end': row['time_end'] or '15:00',
                'is_active': int(row['is_active']),
                'use_backtest': int(row['use_backtest']),
                'use_realtime': int(row['use_realtime']),
                'use_replay': int(row['use_replay']),
                'created_at': str(row['created_at']) if pd.notna(row['created_at']) else '',
                'updated_at': str(row['updated_at']) if pd.notna(row['updated_at']) else ''
            })
        
        return jsonify({'success': True, 'schemes': schemes})
        
    except Exception as e:
        print(f"[quant-schemes] 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@monitor_bp.route('/quant-schemes', methods=['POST'])
def save_quant_scheme():
    """保存方案（新增或覆盖）"""
    from sqlalchemy import text
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '请求体为空'}), 400
    
    scheme_name = data.get('scheme_name', '').strip()
    if not scheme_name:
        return jsonify({'success': False, 'error': '方案名称不能为空'}), 400
    
    try:
        engine = _get_shared_engine()
        
        conditions = data.get('conditions', [])
        conditions_json = json.dumps(conditions, ensure_ascii=False)
        
        sql = text("""
            INSERT INTO quant_screen_schemes 
            (scheme_name, scheme_desc, conditions_json, stop_loss_pct, take_profit_pct, max_hold_time,
             price_offset, offset_mode, time_start, time_end,
             is_active, use_backtest, use_realtime, use_replay)
            VALUES 
            (:scheme_name, :scheme_desc, :conditions_json, :stop_loss_pct, :take_profit_pct, :max_hold_time,
             :price_offset, :offset_mode, :time_start, :time_end,
             :is_active, :use_backtest, :use_realtime, :use_replay)
            ON DUPLICATE KEY UPDATE
                scheme_desc = VALUES(scheme_desc),
                conditions_json = VALUES(conditions_json),
                stop_loss_pct = VALUES(stop_loss_pct),
                take_profit_pct = VALUES(take_profit_pct),
                max_hold_time = VALUES(max_hold_time),
                price_offset = VALUES(price_offset),
                offset_mode = VALUES(offset_mode),
                time_start = VALUES(time_start),
                time_end = VALUES(time_end),
                is_active = VALUES(is_active),
                use_backtest = VALUES(use_backtest),
                use_realtime = VALUES(use_realtime),
                use_replay = VALUES(use_replay)
        """)
        
        with engine.connect() as conn:
            conn.execute(sql, {
                'scheme_name': scheme_name,
                'scheme_desc': data.get('scheme_desc', ''),
                'conditions_json': conditions_json,
                'stop_loss_pct': data.get('stop_loss_pct', 3.0),
                'take_profit_pct': data.get('take_profit_pct', 5.0),
                'max_hold_time': data.get('max_hold_time', 30),
                'price_offset': data.get('price_offset', 0.0),
                'offset_mode': data.get('offset_mode', 'fixed'),
                'time_start': data.get('time_start', '09:30'),
                'time_end': data.get('time_end', '15:00'),
                'is_active': data.get('is_active', 1),
                'use_backtest': data.get('use_backtest', 1),
                'use_realtime': data.get('use_realtime', 1),
                'use_replay': data.get('use_replay', 1)
            })
            conn.commit()
        
        return jsonify({'success': True, 'message': '方案保存成功'})
        
    except Exception as e:
        print(f"[quant-schemes] 保存失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@monitor_bp.route('/quant-schemes/<int:scheme_id>/status', methods=['PUT'])
def update_scheme_status(scheme_id):
    """更新方案状态（在用/停用）"""
    from sqlalchemy import text
    
    data = request.get_json()
    is_active = data.get('is_active')
    
    if is_active not in [0, 1]:
        return jsonify({'success': False, 'error': 'is_active必须是0或1'}), 400
    
    try:
        engine = _get_shared_engine()
        
        sql = text("""
            UPDATE quant_screen_schemes 
            SET is_active = :is_active 
            WHERE id = :id
        """)
        
        with engine.connect() as conn:
            result = conn.execute(sql, {'is_active': is_active, 'id': scheme_id})
            conn.commit()
            
            if result.rowcount == 0:
                return jsonify({'success': False, 'error': '方案不存在'}), 404
        
        return jsonify({'success': True, 'message': '状态更新成功'})
        
    except Exception as e:
        print(f"[quant-schemes] 更新状态失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


