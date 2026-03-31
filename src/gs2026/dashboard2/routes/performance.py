"""
性能监控路由
接收前端慢资源上报，提供历史统计数据
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

performance_bp = Blueprint('performance', __name__)


@performance_bp.route('/api/performance/slow-frontend', methods=['POST'])
def report_slow_frontend():
    """
    接收前端慢资源上报

    Request Body:
        {
            'resource_type': 'xhr',
            'url': 'http://localhost:8080/api/...',
            'duration_ms': 1200,
            'transfer_size': 1024,
            'page_url': 'http://localhost:8080/monitor',
            'extra_info': {...}
        }

    Returns:
        {'success': True} 或 {'success': False, 'error': '...'}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # 验证必需字段
        if 'resource_type' not in data or 'url' not in data or 'duration_ms' not in data:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        # 保存到数据库（异步）
        from gs2026.dashboard2.services.slow_log_service import SlowLogService
        SlowLogService().save_slow_frontend_resource_async(data)

        return jsonify({'success': True})

    except Exception as e:
        # 保存失败不影响前端响应
        return jsonify({'success': False, 'error': str(e)}), 500


@performance_bp.route('/api/performance/slow-stats', methods=['GET'])
def get_slow_stats():
    """
    获取慢请求/查询/前端资源统计

    Query Params:
        date: 日期字符串 'YYYY-MM-DD'，可选，默认今天

    Returns:
        {
            'slow_requests': {'total': 0, 'avg_duration': 0, 'max_duration': 0},
            'slow_queries': {'total': 0, 'avg_duration': 0, 'max_duration': 0},
            'slow_frontend': {'total': 0, 'avg_duration': 0, 'max_duration': 0}
        }
    """
    try:
        date = request.args.get('date')

        # 如果没有提供日期，使用今天
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')

        from gs2026.dashboard2.services.slow_log_service import SlowLogService
        stats = SlowLogService().get_stats(date)

        return jsonify({
            'success': True,
            'date': date,
            'stats': stats
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@performance_bp.route('/api/performance/slow-requests', methods=['GET'])
def get_slow_requests():
    """
    获取慢请求列表

    Query Params:
        date: 日期字符串 'YYYY-MM-DD'，可选
        limit: 返回条数，默认50

    Returns:
        {'success': True, 'data': [...]}
    """
    try:
        date = request.args.get('date')
        limit = request.args.get('limit', 50, type=int)

        from gs2026.dashboard2.services.slow_log_service import SlowLogService
        data = SlowLogService().get_slow_requests(date, limit)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@performance_bp.route('/api/performance/slow-queries', methods=['GET'])
def get_slow_queries():
    """
    获取慢查询列表

    Query Params:
        date: 日期字符串 'YYYY-MM-DD'，可选
        limit: 返回条数，默认50

    Returns:
        {'success': True, 'data': [...]}
    """
    try:
        date = request.args.get('date')
        limit = request.args.get('limit', 50, type=int)

        from gs2026.dashboard2.services.slow_log_service import SlowLogService
        data = SlowLogService().get_slow_queries(date, limit)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@performance_bp.route('/api/performance/slow-frontend', methods=['GET'])
def get_slow_frontend():
    """
    获取前端慢资源列表

    Query Params:
        date: 日期字符串 'YYYY-MM-DD'，可选
        limit: 返回条数，默认50

    Returns:
        {'success': True, 'data': [...]}
    """
    try:
        date = request.args.get('date')
        limit = request.args.get('limit', 50, type=int)

        from gs2026.dashboard2.services.slow_log_service import SlowLogService
        data = SlowLogService().get_slow_frontend_resources(date, limit)

        return jsonify({
            'success': True,
            'data': data
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@performance_bp.route('/api/performance/hotspot', methods=['GET'])
def get_hotspot():
    """
    获取热点分析（最慢的API/SQL/前端资源）

    Query Params:
        days: 分析最近N天，默认7

    Returns:
        {
            'success': True,
            'data': {
                'api': [...],
                'sql': [...],
                'frontend': [...]
            }
        }
    """
    try:
        days = request.args.get('days', 7, type=int)

        from gs2026.dashboard2.services.slow_log_service import SlowLogService
        data = SlowLogService().get_hotspot_analysis(days)

        return jsonify({
            'success': True,
            'days': days,
            'data': data
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
