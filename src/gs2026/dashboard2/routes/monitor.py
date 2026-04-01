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


@monitor_bp.route('/attack-ranking/stock', methods=['GET'])
def get_stock_ranking():
    """获取股票上攻排行（含债券/行业信息）"""
    try:
        date = request.args.get('date')
        limit = int(request.args.get('limit', 60))
        use_mysql = _is_historical(date)

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
                # 添加涨跌幅
                data = _enrich_change_pct(data, date, '15:00:00')
                return jsonify({
                    'success': True,
                    'data': data,
                    'count': len(data),
                    'type': 'stock',
                    'note': '已自动回退到15:00:00数据'
                })

        # 获取原始股票数据
        data = data_service.get_stock_ranking(limit=limit, date=date, use_mysql=use_mysql)
        
        # 补充债券和行业信息
        data = _enrich_stock_data(data)

        # 添加涨跌幅
        actual_date = date or datetime.now().strftime('%Y%m%d')
        data = _enrich_change_pct(data, actual_date)

        return jsonify({
            'success': True,
            'data': data,
            'count': len(data),
            'type': 'stock'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'type': 'stock'
        }), 500


@monitor_bp.route('/attack-ranking/bond', methods=['GET'])
def get_bond_ranking():
    """获取债券上攻排行"""
    try:
        date = request.args.get('date')
        limit = int(request.args.get('limit', 30))
        use_mysql = _is_historical(date)
        data = data_service.get_bond_ranking(limit=limit, date=date, use_mysql=use_mysql)
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
