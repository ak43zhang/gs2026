"""
监控数据路由 - 支持股票、债券、行业三个排行榜
"""
from datetime import datetime
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache

monitor_bp = Blueprint('monitor', __name__)
data_service = DataService()


def _enrich_stock_data(stocks: list) -> list:
    """
    为股票数据添加债券和行业信息
    
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
        
        # 确保缓存存在（不强制更新，避免阻塞）
        if not cache.ensure_cache():
            # 缓存创建失败，返回原始数据（带空字段）
            for stock in stocks:
                stock['bond_code'] = '-'
                stock['bond_name'] = '-'
                stock['industry_name'] = '-'
            return stocks
        
        # 批量获取所有映射（1次Redis查询替代60次）
        stock_codes = [stock.get('code', '') for stock in stocks]
        mappings = cache.get_mappings_batch(stock_codes)

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

        if df is not None and not df.empty:
            # 构建字典 {bond_code: change_pct}
            code_col = 'bond_code' if 'bond_code' in df.columns else 'code'
            change_col = 'change_pct'

            df[code_col] = df[code_col].astype(str)
            return df.set_index(code_col)[change_col].to_dict()

        # 2. Redis未命中，从MySQL查询
        return _get_bond_change_pct_from_mysql(date, time_str, bond_codes)

    except Exception as e:
        print(f"批量获取债券涨跌幅失败: {e}")
        return {}


def _get_bond_change_pct_from_mysql(date: str, time_str: str, bond_codes: list) -> dict:
    """从MySQL批量查询债券涨跌幅"""
    try:
        from sqlalchemy import create_engine, text
        from ..config import Config

        engine = create_engine(Config.MYSQL_URI)
        table_name = f"monitor_zq_sssj_{date}"

        # 批量查询（使用IN语句）
        codes_str = ','.join([f"'{code}'" for code in bond_codes])
        sql = text(f"""
            SELECT bond_code, change_pct
            FROM {table_name}
            WHERE time = :time_str AND bond_code IN ({codes_str})
        """)

        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={'time_str': time_str})
            if not df.empty:
                df['bond_code'] = df['bond_code'].astype(str)
                return df.set_index('bond_code')['change_pct'].to_dict()

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
            bond['change_pct'] = change_pct_map.get(code, '-')
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
            # 获取最新时间戳
            sssj_table = f"monitor_gp_sssj_{date}"
            ts_key = f"{sssj_table}:timestamps"
            latest_ts = client.lindex(ts_key, 0)
            if latest_ts:
                query_time = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
            else:
                # 无时间戳数据，全部设为"-"
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
            # 获取最新时间戳
            sssj_table = f"monitor_gp_sssj_{date}"
            ts_key = f"{sssj_table}:timestamps"
            latest_ts = client.lindex(ts_key, 0)
            if latest_ts:
                query_time = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
            else:
                for stock in stocks:
                    stock['change_pct'] = '-'
                    stock['main_net_amount'] = 0
                return stocks

        # 提取所有股票代码
        stock_codes = [s['code'].zfill(6) for s in stocks if s.get('code')]

        # 批量获取涨跌幅和主力净额（1次查询）
        change_pct_map, main_net_map = _get_change_pct_and_main_net_batch(date, query_time, stock_codes)
        
        # 【新增】获取累计主力净额（从开盘到当前时间）
        cumulative_main_net_map = _get_cumulative_main_net_batch(date, query_time, stock_codes)

        # 填充数据
        for stock in stocks:
            code = stock.get('code', '').zfill(6)
            
            # 涨跌幅（当前时间点）
            change_pct = change_pct_map.get(code)
            stock['change_pct'] = change_pct if change_pct is not None else '-'
            
            # 主力净额（使用新的 cumulative_main_net 字段）
            # 优先从 cumulative_main_net_map 获取，如果没有则尝试 main_net_map
            cumulative_main_net = cumulative_main_net_map.get(code)
            if cumulative_main_net is not None:
                stock['main_net_amount'] = cumulative_main_net
            else:
                # 回退到单条记录值（兼容旧数据）
                current_main_net = main_net_map.get(code)
                stock['main_net_amount'] = current_main_net if current_main_net is not None else 0

        return stocks

    except Exception as e:
        print(f"添加涨跌幅和主力净额失败: {e}")
        for stock in stocks:
            stock['change_pct'] = '-'
            stock['main_net_amount'] = 0
        return stocks


def _get_change_pct_and_main_net_batch(date: str, time_str: str, stock_codes: list) -> tuple:
    """
    批量获取涨跌幅和主力净额
    【新增函数】
    返回: (change_pct_map, main_net_map)
    """
    import pandas as pd
    from gs2026.utils import redis_util
    
    if not stock_codes:
        return {}, {}
    
    change_pct_map = {}
    main_net_map = {}
    
    try:
        # 1. 优先从Redis批量获取
        sssj_table = f"monitor_gp_sssj_{date}"
        redis_key = f"{sssj_table}:{time_str}"
        
        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
        
        if df is not None and not df.empty:
            # 构建字典
            code_col = 'stock_code' if 'stock_code' in df.columns else 'code'
            df[code_col] = df[code_col].astype(str).str.zfill(6)
            
            # 涨跌幅
            if 'change_pct' in df.columns:
                for _, row in df.iterrows():
                    code = str(row[code_col]).zfill(6)
                    if row['change_pct'] is not None:
                        change_pct_map[code] = float(row['change_pct'])
            
            # 主力净额
            if 'main_net_amount' in df.columns:
                for _, row in df.iterrows():
                    code = str(row[code_col]).zfill(6)
                    if row['main_net_amount'] is not None:
                        main_net_map[code] = float(row['main_net_amount'])
                    else:
                        main_net_map[code] = 0
                # Redis中有主力净额数据，直接返回
                return change_pct_map, main_net_map
            # 如果Redis中没有主力净额字段，继续走MySQL查询
        
        # 2. Redis未命中或没有主力净额字段，从MySQL查询
        from sqlalchemy import create_engine, text
        from ..config import Config
        
        engine = create_engine(Config.MYSQL_URI)
        codes_str = ','.join([f"'{c}'" for c in stock_codes])
        table_name = f"monitor_gp_sssj_{date}"
        
        query = f"""
            SELECT stock_code, change_pct, main_net_amount, cumulative_main_net
            FROM {table_name}
            WHERE time = '{time_str}' AND stock_code IN ({codes_str})
        """
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
            for _, row in df.iterrows():
                code = str(row['stock_code']).zfill(6)
                # 涨跌幅
                if row['change_pct'] is not None:
                    change_pct_map[code] = float(row['change_pct'])
                # 主力净额（优先使用累计值）
                if row['cumulative_main_net'] is not None:
                    main_net_map[code] = float(row['cumulative_main_net'])
                elif row['main_net_amount'] is not None:
                    main_net_map[code] = float(row['main_net_amount'])
                else:
                    main_net_map[code] = 0
                    
    except Exception as e:
        print(f"批量查询涨跌幅和主力净额失败: {e}")
    
    return change_pct_map, main_net_map


def _get_cumulative_main_net_batch(date: str, time_str: str, stock_codes: list) -> dict:
    """
    批量获取累计主力净额（从开盘到指定时间）
    【新增函数】
    返回: {stock_code: cumulative_main_net} 字典
    """
    import pandas as pd
    from sqlalchemy import create_engine, text
    from ..config import Config
    
    if not stock_codes:
        return {}
    
    cumulative_main_net_map = {}
    
    try:
        engine = create_engine(Config.MYSQL_URI)
        codes_str = ','.join([f"'{c}'" for c in stock_codes])
        table_name = f"monitor_gp_sssj_{date}"
        
        # 查询从开盘到指定时间的累计主力净额
        query = f"""
            SELECT stock_code, SUM(main_net_amount) as cumulative_main_net
            FROM {table_name}
            WHERE time <= '{time_str}' AND stock_code IN ({codes_str})
            GROUP BY stock_code
        """
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
            for _, row in df.iterrows():
                code = str(row['stock_code']).zfill(6)
                if row['cumulative_main_net'] is not None:
                    cumulative_main_net_map[code] = float(row['cumulative_main_net'])
                else:
                    cumulative_main_net_map[code] = 0
                    
    except Exception as e:
        print(f"批量查询累计主力净额失败: {e}")
    
    return cumulative_main_net_map


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
        use_mysql = _is_historical(date)
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
        use_mysql = _is_historical(date)
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
        use_mysql = _is_historical(date)
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
        use_mysql = _is_historical(date)
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
        use_mysql = _is_historical(date)
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

def _get_latest_sssj_time(date: str, asset_type: str = 'bond') -> str:
    """
    获取最新的实时数据时间（使用 timestamps list，与股票一致）
    
    Args:
        date: 日期 YYYYMMDD
        asset_type: 'bond' 或 'stock'
    
    Returns:
        最新时间 HH:MM:SS，如果没有数据返回 None
    """
    try:
        from gs2026.utils import redis_util
        
        # 使用 timestamps list 获取最新时间（与 _enrich_bond_data 一致）
        table_prefix = 'monitor_zq_sssj' if asset_type == 'bond' else 'monitor_gp_sssj'
        ts_key = f"{table_prefix}_{date}:timestamps"
        
        client = redis_util._get_redis_client()
        latest_ts = client.lindex(ts_key, 0)
        
        if latest_ts:
            return latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
        
        return None
    except Exception as e:
        print(f"获取最新实时数据时间失败: {e}")
        return None


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
            # 获取最新时间（从timestamps list）
            available_time = _get_latest_sssj_time(date, 'bond')
            import logging
            logging.warning(f"[DEBUG] 指定时间 {time_str} 无数据，最新时间: {available_time}")
            if available_time:
                # 无论是否相同，都尝试用最新时间查询
                redis_key = f"{sssj_table}:{available_time}"
                logging.warning(f"[DEBUG] 尝试查询: {redis_key}")
                df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
                logging.warning(f"[DEBUG] 查询结果: {df is not None and not df.empty}")

        if df is not None and not df.empty:
            # 构建字典 {bond_code: change_pct}
            code_col = 'bond_code' if 'bond_code' in df.columns else 'code'
            change_col = 'change_pct'
            
            # 关键修复：确保代码列为字符串类型，去除小数点
            df[code_col] = df[code_col].astype(str).str.replace('.0', '', regex=False)
            
            result = df.set_index(code_col)[change_col].to_dict()
            return result

        # 2. Redis未命中，从MySQL查询
        return _get_bond_change_pct_from_mysql(date, time_str, bond_codes)

    except Exception as e:
        print(f"批量获取债券涨跌幅失败: {e}")
        return {}


def _get_bond_change_pct_from_mysql(date: str, time_str: str, bond_codes: list) -> dict:
    """从MySQL批量查询债券涨跌幅"""
    try:
        from sqlalchemy import create_engine, text
        from ..config import Config

        engine = create_engine(Config.MYSQL_URI)
        table_name = f"monitor_zq_sssj_{date}"

        # 批量查询（使用IN语句）
        codes_str = ','.join([f"'{code}'" for code in bond_codes])
        sql = text(f"""
            SELECT bond_code, change_pct
            FROM {table_name}
            WHERE time = :time_str AND bond_code IN ({codes_str})
        """)

        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={'time_str': time_str})
            if not df.empty:
                df['bond_code'] = df['bond_code'].astype(str)
                return df.set_index('bond_code')['change_pct'].to_dict()

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
            # 获取最新时间戳（和股票一样，使用 timestamps list）
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
            bond['change_pct'] = change_pct_map.get(code, '-')
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
            # 获取最新时间戳
            sssj_table = f"monitor_zq_sssj_{date}"
            ts_key = f"{sssj_table}:timestamps"
            latest_ts = client.lindex(ts_key, 0)
            if latest_ts:
                query_time = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
            else:
                # 无时间戳数据，全部标记为非实时
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
