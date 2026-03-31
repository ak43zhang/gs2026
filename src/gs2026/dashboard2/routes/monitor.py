"""
监控数据路由 - 支持股票、债券、行业三个排行榜
"""
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template
import sys
from pathlib import Path
import yaml

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache


def _load_frontend_perf_config():
    """加载前端性能监控配置"""
    try:
        config_path = Path(__file__).parent.parent.parent.parent / 'configs' / 'settings.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('frontend_perf', {})
    except Exception:
        pass
    return {'enabled': False}

monitor_bp = Blueprint('monitor', __name__)
data_service = DataService()


def _enrich_stock_data(stocks: list) -> list:
    """
    为股票数据添加债券和行业信息（批量查询优化）
    
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


def _enrich_change_pct(stocks: list, date: str, time_str: str = None) -> list:
    """
    为股票数据添加涨跌幅（向量化优化版）
    
    从Redis的monitor_gp_top30表获取指定时间的change_pct_now
    
    Args:
        stocks: 股票数据列表
        date: 日期 YYYYMMDD
        time_str: 时间点 HH:MM:SS（可选）
    
    Returns:
        添加涨跌幅后的股票数据列表
    """
    if not stocks:
        return stocks
    
    try:
        from gs2026.utils import redis_util
        client = redis_util._get_redis_client()
        
        # 构建表名
        table_name = f"monitor_gp_top30_{date}"
        
        # 确定查询时间
        if time_str:
            query_time = time_str
        else:
            ts_key = f"{table_name}:timestamps"
            latest_ts = client.lindex(ts_key, 0)
            if latest_ts:
                query_time = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
            else:
                for stock in stocks:
                    stock['change_pct'] = None
                return stocks
        
        # 从Redis获取该时间点的DataFrame
        redis_key = f"{table_name}:{query_time}"
        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
        
        if df is None or df.empty:
            for stock in stocks:
                stock['change_pct'] = None
            return stocks
        
        # 向量化优化：使用pandas的map替代循环
        # 1. 确定涨跌幅列
        change_col = 'change_pct_now' if 'change_pct_now' in df.columns else 'change_pct'
        
        # 2. 格式化code列（确保6位）
        df['code'] = df['code'].astype(str).str.zfill(6)
        
        # 3. 使用set_index和to_dict构建映射（比循环快10倍）
        change_pct_map = df.set_index('code')[change_col].to_dict()
        
        # 4. 批量填充（使用列表推导式）
        stock_codes = [s['code'].zfill(6) for s in stocks]
        change_pcts = [change_pct_map.get(code) for code in stock_codes]
        
        for stock, change_pct in zip(stocks, change_pcts):
            stock['change_pct'] = change_pct
        
        return stocks
        
    except Exception as e:
        # 出错时返回原数据
        for stock in stocks:
            stock['change_pct'] = None
        return stocks


def _process_stock_ranking(data: list, date: str = None, time_str: str = None) -> list:
    """
    统一处理股票排行数据：
    - 补充债券/行业信息
    - 标记红名单
    - 添加涨跌幅
    - 红名单优先排序
    
    Args:
        data: 原始股票数据列表
        date: 日期 YYYYMMDD（可选）
        time_str: 时间点 HH:MM:SS（可选）
    
    Returns:
        处理后的股票数据列表
    """
    if not data:
        return data
    
    # 补充债券和行业信息
    data = _enrich_stock_data(data)
    
    # 确定实际日期：如果date为None，使用当前日期（不自动切换）
    actual_date = date or datetime.now().strftime('%Y%m%d')
    
    # 添加涨跌幅
    data = _enrich_change_pct(data, actual_date, time_str)
    
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
    
    return data


@monitor_bp.route('/attack-ranking/stock', methods=['GET'])
def get_stock_ranking():
    """
    获取股票上攻排行（统一接口，支持实时和时间轴）
    
    Query Params:
        date: 日期 YYYYMMDD（可选，默认今天）
        time: 时间点 HH:MM:SS（可选，有则查询该时间点数据）
        limit: 返回条数，默认60
    """
    try:
        date = request.args.get('date')
        time_str = request.args.get('time')  # 时间点参数
        limit = int(request.args.get('limit', 60))
        
        # 特殊处理：如果未指定时间且当前时间 > 15:00:00，自动使用15:00:00
        if not time_str and not date:
            now = datetime.now().strftime('%H:%M:%S')
            if now > '15:00:00':
                time_str = '15:00:00'
        
        if time_str:
            # 时间点查询（时间轴回放）
            data = data_service.get_ranking_at_time(
                asset_type='stock', limit=limit,
                date=date, time_str=time_str
            )
        else:
            # 实时/日期查询
            use_mysql = _is_historical(date)
            data = data_service.get_stock_ranking(
                limit=limit, date=date, use_mysql=use_mysql
            )
        
        # 统一处理股票数据（债券/行业信息、涨跌幅、红名单标记、排序）
        data = _process_stock_ranking(data, date, time_str)
        
        return jsonify({
            'success': True,
            'data': data,
            'count': len(data),
            'type': 'stock',
            'time': time_str  # 返回时间点（如果有）
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'type': 'stock'
        }), 500
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
    获取某个时间点的上攻排行（已废弃，请使用 /attack-ranking/stock?time=HH:MM:SS）
    
    保留此接口用于向后兼容
    """
    try:
        date = request.args.get('date')
        time_str = request.args.get('time')
        limit = int(request.args.get('limit', 60))  # 统一默认60
        
        if asset_type == 'stock':
            # 股票类型：复用统一处理函数
            data = data_service.get_ranking_at_time(
                asset_type='stock', limit=limit,
                date=date, time_str=time_str
            )
            data = _process_stock_ranking(data, date, time_str)
        else:
            # 债券/行业：直接查询
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


def _get_next_update_time(now: datetime, is_auction: bool) -> str:
    """计算下次更新时间"""
    if is_auction:
        # 集合竞价期间：5分钟后
        next_time = now + timedelta(minutes=5)
    else:
        # 正常交易：3秒后
        next_time = now + timedelta(seconds=3)
    return next_time.strftime('%H:%M:%S')


@monitor_bp.route('/market-overview', methods=['GET'])
def get_market_overview():
    """获取大盘数据（增强版：支持集合竞价状态）"""
    try:
        date = request.args.get('date')
        time_str = request.args.get('time')
        use_mysql = _is_historical(date)
        data = data_service.get_market_stats(date=date, use_mysql=use_mysql, time_str=time_str)

        # 添加集合竞价状态
        now = datetime.now()
        is_auction, auction_period = is_in_auction_period(now.time())

        return jsonify({
            'success': True,
            'data': data,
            'meta': {
                'is_auction': is_auction,
                'auction_period': auction_period,  # 'morning' | 'afternoon' | null
                'next_update': _get_next_update_time(now, is_auction),
                'update_interval': 300 if is_auction else 3  # 秒
            }
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
