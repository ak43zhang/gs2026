"""公告分析API路由"""

from flask import Blueprint, request, jsonify

from gs2026.dashboard2.services import notice_analysis_service

notice_bp = Blueprint('notice', __name__)


@notice_bp.route('/api/notice/list')
def notice_list():
    """公告列表"""
    try:
        date = request.args.get('date')
        stock_code = request.args.get('stock_code')
        stock_name = request.args.get('stock_name')
        search = request.args.get('search')
        risk_level = request.args.get('risk_level')
        notice_type = request.args.get('notice_type')
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        
        result = notice_analysis_service.get_notice_list(
            date=date,
            stock_code=stock_code,
            stock_name=stock_name,
            search=search,
            risk_level=risk_level,
            notice_type=notice_type,
            page=page,
            page_size=page_size
        )
        
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@notice_bp.route('/api/notice/detail/<content_hash>')
def notice_detail(content_hash):
    """公告详情"""
    try:
        result = notice_analysis_service.get_notice_detail(content_hash)
        if result:
            return jsonify({'code': 0, 'message': 'success', 'data': result})
        return jsonify({'code': 404, 'message': '不存在', 'data': None}), 404
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@notice_bp.route('/api/notice/stats')
def notice_stats():
    """公告统计"""
    try:
        date = request.args.get('date')
        result = notice_analysis_service.get_notice_stats(date)
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500
