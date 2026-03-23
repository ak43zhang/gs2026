"""
监控数据路由
"""
from flask import Blueprint, jsonify
from gs2026.dashboard.services.data_service import DataService

monitor_bp = Blueprint('monitor', __name__)
data_service = DataService()


@monitor_bp.route('/attack-ranking', methods=['GET'])
def get_attack_ranking():
    """获取上攻排行数据"""
    try:
        data = data_service.get_attack_ranking()
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


@monitor_bp.route('/market-overview', methods=['GET'])
def get_market_overview():
    """获取大盘数据"""
    try:
        data = data_service.get_market_overview()
        return jsonify({
            'success': True,
            'data': data
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
        data = data_service.get_sector_distribution()
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
        data = data_service.get_latest_messages(limit)
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
