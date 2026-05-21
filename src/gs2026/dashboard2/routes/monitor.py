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

             bond_code, bond_price, bond_change_pct, level, condition_count, total_conditions,

             conditions, market_context)

            VALUES (:record_id, :date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,

             :bond_code, :bond_price, :bond_change_pct, :level, :condition_count, :total_conditions,

             :conditions, :market_context)

            ON DUPLICATE KEY UPDATE

            stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),

            bond_price=VALUES(bond_price), bond_change_pct=VALUES(bond_change_pct),

            level=VALUES(level), condition_count=VALUES(condition_count),

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

    为股票数据添加债券和行业信息（三层缓存策略优化版）



    Args:

        stocks: 原始股票数据列表



    Returns:

        添加债券/行业信息后的股票数据列表

    """

    if not stocks:

        return stocks



    try:

        # 获取映射缓存

        cache = get_cache()



        # 【优化】使用三层缓存策略获取映射

        stock_codes = [stock.get('code', '') for stock in stocks if stock.get('code')]

        mappings = cache.get_mappings_smart(stock_codes)



        # 填充数据

        for stock in stocks:

            stock_code = stock.get('code', '')

            mapping = mappings.get(stock_code)



            if mapping:

                stock['bond_code'] = mapping.get('bond_code', '-')

                stock['bond_name'] = mapping.get('bond_name', '-')

                stock['industry_name'] = mapping.get('industry_name', '-')

            else:

                stock['bond_code'] = '-'

                stock['bond_name'] = '-'

                stock['industry_name'] = '-'



        return stocks



    except Exception as e:

        # 出错时返回原始数据（带空字段）

        for stock in stocks:

            stock['bond_code'] = '-'

            stock['bond_name'] = '-'

            stock['industry_name'] = '-'

        return stocks





def _is_historical(date: str | None) -> bool:

    """判断传入的日期是否为历史日期（非今天），历史日期需要走 MySQL"""

    if not date:

        return False

    today = datetime.now().strftime('%Y%m%d')

    return date != today





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



        # 如果指定时间不存在，尝试查找最近的时间

        if df is None or df.empty:

            available_time = _get_latest_sssj_time(date, 'bond')

            if available_time:

                redis_key = f"{sssj_table}:{available_time}"

                df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)



        if df is not None and not df.empty:

            # 构建字典 {bond_code: change_pct}

            code_col = 'bond_code' if 'bond_code' in df.columns else 'code'

            change_col = 'change_pct'



            df[code_col] = df[code_col].astype(str)

            result = df.set_index(code_col)[change_col].to_dict()



            # 同时提取价格字段

            if 'price' in df.columns:

                price_map = df.set_index(code_col)['price'].to_dict()

                for code in result:

                    result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}



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

            SELECT bond_code, change_pct, price

            FROM {table_name}

            WHERE time = :time_str AND bond_code IN ({codes_str})

        """)



        with engine.connect() as conn:

            df = pd.read_sql(sql, conn, params={'time_str': time_str})

            if not df.empty:

                df['bond_code'] = df['bond_code'].astype(str)

                result = df.set_index('bond_code')['change_pct'].to_dict()

                # 同时提取价格

                if 'price' in df.columns:

                    price_map = df.set_index('bond_code')['price'].to_dict()

                    for code in result:

                        result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}

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



        # 填充数据

        for bond in bonds:

            code = bond.get('code', '')

            # 涨跌幅和价格（新格式是dict，旧格式是scalar）

            val = change_pct_map.get(code, '-')

            if isinstance(val, dict):

                bond['change_pct'] = val.get('change_pct', '-')

                bond['price'] = val.get('price', '-')

            else:

                bond['change_pct'] = val

                bond['price'] = '-'

            bond['industry_name'] = industry_map.get(code, '-')



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

            for _, row in df.iterrows():

                code = str(row['stock_code']).zfill(6)

                if row['change_pct'] is not None:

                    change_pct_map[code] = float(row['change_pct'])

                if pd.notna(row['cumulative_main_net']) and row['cumulative_main_net'] != 0:

                    main_net_map[code] = float(row['cumulative_main_net'])

                else:

                    main_net_map[code] = 0

            # 提取派生字段

            _extract_derived(df, 'stock_code')



    except Exception as e:

        print(f"批量查询涨跌幅和主力净额失败: {e}")



    return change_pct_map, main_net_map, derived_maps





@monitor_bp.route('/attack-ranking/stock', methods=['GET'])

def get_stock_ranking():

    """获取股票上攻排行（含债券/行业信息，支持实时和时间轴）"""

    try:

        date = request.args.get('date')

        time_str = request.args.get('time')  # 时间轴参数

        limit = int(request.args.get('limit', 60))

        use_mysql = _is_historical(date)



        # 如果时间参数存在，使用 at-time 查询（时间轴模式）

        if time_str:

            actual_date = date or datetime.now().strftime('%Y%m%d')

            data = data_service.get_ranking_at_time(

                asset_type='stock', limit=limit,

                date=actual_date, time_str=time_str

            )

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



        # 特殊处理：如果未指定时间且当前时间 > 15:00:00，自动使用15:00:00

        if not date:

            now = datetime.now().strftime('%H:%M:%S')

            if now > '15:00:00':

                date = datetime.now().strftime('%Y%m%d')

                data = data_service.get_ranking_at_time(

                    asset_type='stock', limit=limit,

                    date=date, time_str='15:00:00'

                )

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



        # 排序：红名单优先，然后按次数倒序

        data.sort(key=lambda x: (-int(x.get('is_red', False)), -x.get('count', 0)))



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

        time_str = request.args.get('time')  # 【新增】时间参数，支持时间轴点击

        limit = int(request.args.get('limit', 30))

        use_mysql = True  # Redis优先，无数据自动回退MySQL（收盘后Redis过期场景）

        data = data_service.get_bond_ranking(limit=limit, date=date, use_mysql=use_mysql)



        # 添加涨跌幅和行业信息

        actual_date = date or datetime.now().strftime('%Y%m%d')

        data = _enrich_bond_data(data, actual_date, time_str)



        # 标记绿名单

        try:

            from gs2026.dashboard2.routes.green_bond_list_cache import get_green_bond_list

            green_bond_list = get_green_bond_list()

            for item in data:

                item['is_green'] = item.get('code', '') in green_bond_list

        except Exception:

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

        limit: 返回条数，默认15

    """

    try:

        date = request.args.get('date')

        time_str = request.args.get('time')

        limit = int(request.args.get('limit', 15))

        data = data_service.get_ranking_at_time(

            asset_type=asset_type, limit=limit,

            date=date, time_str=time_str

        )



        # 【修复】为债券数据添加涨跌幅和行业信息

        if asset_type == 'bond' and data and time_str:

            actual_date = date or datetime.now().strftime('%Y%m%d')

            data = _enrich_bond_data(data, actual_date, time_str)



            # 【新增】标记绿名单

            try:

                from gs2026.dashboard2.routes.green_bond_list_cache import get_green_bond_list

                green_bond_list = get_green_bond_list()

                for item in data:

                    item['is_green'] = item.get('code', '') in green_bond_list

            except Exception:

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





@monitor_bp.route('/market-overview', methods=['GET'])

def get_market_overview():

    """获取大盘数据"""

    try:

        date = request.args.get('date')

        time_str = request.args.get('time')

        use_mysql = True  # Redis优先，无数据自动回退MySQL（收盘后Redis过期场景）

        data = data_service.get_market_stats(date=date, use_mysql=use_mysql, time_str=time_str)

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

        data = data_service.get_combine_ranking(limit=limit, date=date, time_str=time_str)

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

            SELECT bond_code, change_pct, price

            FROM {table_name}

            WHERE time = :time_str AND bond_code IN ({codes_str})

        """)



        with engine.connect() as conn:

            df = pd.read_sql(sql, conn, params={'time_str': time_str})

            if not df.empty:

                df['bond_code'] = df['bond_code'].astype(str)

                result = df.set_index('bond_code')['change_pct'].to_dict()

                # 同时提取价格

                if 'price' in df.columns:

                    price_map = df.set_index('bond_code')['price'].to_dict()

                    for code in result:

                        result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}

                return result



        return {}



    except Exception as e:

        print(f"MySQL批量查询债券涨跌幅失败: {e}")

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

            else:

                bond['change_pct'] = val

                bond['price'] = '-'

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

            bond['is_realtime'] = code in realtime_codes



        # 排序：实时数据优先，然后按次数降序

        bonds.sort(key=lambda x: (not x.get('is_realtime', False), -x.get('count', 0)))



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

        ts_sec = _time_to_seconds(ts)

        diff = abs(ts_sec - target_sec)

        if diff < best_diff and diff < 300:

            best_diff = diff

            best_price = price

    return best_price



def _find_close_price(prices):

    """取最后一条价格作为收盘价"""

    if not prices:

        return None

    return prices[-1][1]





@monitor_bp.route('/buy-points/generate-effects', methods=['POST'])

def generate_effects():

    """为指定日期的买点候选填充效果追踪数据"""

    from sqlalchemy import text

    try:

        data = request.get_json(silent=True) or {}

        target_date = data.get('date', '')

        if not target_date:

            return jsonify(success=False, message='缺少date参数'), 400



        save_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}" if len(target_date) == 8 and '-' not in target_date else target_date



        engine = _get_shared_engine()

        filled = 0

        skipped = 0

        details = []



        with engine.connect() as conn:

            candidates = conn.execute(text("""

                SELECT record_id, stock_code, stock_name, stock_price, time, level

                FROM buy_point_candidates WHERE date = :d

                ORDER BY time DESC

            """), {'d': save_date}).fetchall()



            if not candidates:

                return jsonify(success=True, filled=0, skipped=0, details=[], stats={})



            codes = list(set(str(c[1]) for c in candidates))

            sssj_data = {}

            placeholders = ','.join(["'" + c + "'" for c in codes])

            rows = conn.execute(text(f"""

                SELECT code, timestamp, price FROM sssj

                WHERE date = :d AND code IN ({placeholders})

                ORDER BY code, timestamp

            """), {'d': save_date}).fetchall()

            for row in rows:

                sssj_data.setdefault(str(row[0]), []).append((_time_to_seconds(row[1]), float(row[2])))



            for c in candidates:

                record_id = c[0]

                code = str(c[1])

                name = c[2]

                signal_price = float(c[3]) if c[3] else None

                signal_time = c[4]

                level = c[5]



                if not signal_price or signal_price <= 0:

                    skipped += 1

                    continue



                prices = sssj_data.get(code, [])

                if not prices:

                    skipped += 1

                    continue



                sig_sec = _time_to_seconds(signal_time)

                p5 = _find_nearest_price(prices, signal_time, 5)

                p15 = _find_nearest_price(prices, signal_time, 15)

                p30 = _find_nearest_price(prices, signal_time, 30)

                pc = _find_close_price(prices)



                def pct(p):

                    if p and signal_price:

                        return round((p - signal_price) / signal_price * 100, 4)

                    return None



                c5, c15, c30, cc = pct(p5), pct(p15), pct(p30), pct(pc)



                conn.execute(text("""

                    UPDATE buy_point_candidates SET

                        after_5m_price=:p5, after_5m_change_pct=:c5,

                        after_15m_price=:p15, after_15m_change_pct=:c15,

                        after_30m_price=:p30, after_30m_change_pct=:c30,

                        after_close_price=:pc, after_close_change_pct=:cc

                    WHERE record_id=:rid

                """), {'p5':p5,'c5':c5,'p15':p15,'c15':c15,

                       'p30':p30,'c30':c30,'pc':pc,'cc':cc,'rid':record_id})

                filled += 1



                details.append({

                    'time': str(signal_time), 'code': code, 'name': name,

                    'signal_price': signal_price, 'level': level,

                    'after_5m': c5, 'after_15m': c15,

                    'after_30m': c30, 'after_close': cc

                })



            conn.commit()



        stats = {}

        for period, key in [('5m','after_5m'), ('15m','after_15m'), ('30m','after_30m'), ('close','after_close')]:

            valid = [d[key] for d in details if d[key] is not None]

            stats[period] = {

                'total': len(valid),

                'success': sum(1 for v in valid if v > 0),

                'success_rate': round(sum(1 for v in valid if v > 0) / len(valid) * 100, 1) if valid else 0,

                'avg_return': round(sum(valid) / len(valid), 4) if valid else 0

            }



        return jsonify(success=True, filled=filled, skipped=skipped,

                       details=details, stats=stats)

    except Exception as e:

        print(f"[generate-effects] {e}")

        import traceback; traceback.print_exc()

        return jsonify(success=False, message=str(e)), 500



        return jsonify(success=False, message=str(e)), 500



@monitor_bp.route('/buy-points/recent', methods=['GET'])
def get_recent_buy_points():
    """获取近期买点候选（去重：每只股票只取最新一条，附带命中次数）"""
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

        with engine.connect() as conn:
            # 构建WHERE条件
            where_clause = "date = :d"
            params = {'d': save_date, 'l': limit}
            if before:
                where_clause += " AND time <= :before"
                params['before'] = before

            # 查询：每只股票最新一条 + 命中次数
            sql = f"""
                WITH latest AS (
                    SELECT stock_code, stock_name, stock_price, stock_change_pct,
                           bond_code, bond_price, bond_change_pct,
                           level, time, condition_count, total_conditions, conditions,
                           ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY time DESC) as rn
                    FROM buy_point_candidates
                    WHERE {where_clause}
                ),
                counts AS (
                    SELECT stock_code, COUNT(*) as hit_count
                    FROM buy_point_candidates
                    WHERE {where_clause}
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
                    'hit_count': row[13] or 1
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

                text(f"SELECT time,stock_code,stock_name,stock_price,stock_change_pct,bond_code,bond_price,bond_change_pct,level,condition_count,total_conditions,conditions FROM buy_point_candidates WHERE date = :d AND time IN ({ts}) ORDER BY time DESC, level DESC, stock_code"),

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

                    'level': row[8], 'condition_count': row[9],

                    'total_conditions': row[10], 'conditions': row[11]

                })



            for t in times:

                if t in time_map:

                    groups.append({'time': t, 'items': time_map[t]})



        return jsonify(success=True, groups=groups)

    except Exception as e:

        print(f'[buy-points/recent] {e}')

        return jsonify(success=False, message=str(e)), 500


