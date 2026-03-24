"""
监控数据路由 - 支持股票、债券、行业三个排行榜
"""
from datetime import datetime
from flask import Blueprint, jsonify, request
from gs2026.dashboard.services.data_service import DataService

monitor_bp = Blueprint('monitor', __name__)
data_service = DataService()


def _is_historical(date: str | None) -> bool:
    """判断传入的日期是否为历史日期（非今天），历史日期需要走 MySQL"""
    if not date:
        return False
    today = datetime.now().strftime('%Y%m%d')
    return date != today


@monitor_bp.route('/attack-ranking/stock', methods=['GET'])
def get_stock_ranking():
    """获取股票上攻排行"""
    try:
        date = request.args.get('date')
        limit = int(request.args.get('limit', 30))
        use_mysql = _is_historical(date)
        print(date,use_mysql)
        data = data_service.get_stock_ranking(limit=limit, date=date, use_mysql=use_mysql)
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
    """获取最新消息"""
    try:
        limit = 50
        date = request.args.get('date')
        data = data_service.get_combine_ranking(limit=limit, date=date)
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
