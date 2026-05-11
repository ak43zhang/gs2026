"""公告分析API路由（V3增强版）"""

from flask import Blueprint, request, jsonify

from gs2026.dashboard2.services import notice_analysis_service

notice_bp = Blueprint('notice', __name__)


@notice_bp.route('/api/notice/list')
def notice_list():
    """公告列表（V3增强：+5筛选条件+评分档位+排序）"""
    try:
        result = notice_analysis_service.get_notice_list(
            date=request.args.get('date'),
            stock_code=request.args.get('stock_code'),
            stock_name=request.args.get('stock_name'),
            search=request.args.get('search'),
            risk_level=request.args.get('risk_level'),
            notice_type=request.args.get('notice_type'),
            notice_category=request.args.get('notice_category'),
            market_expectation=request.args.get('market_expectation'),
            open_prediction=request.args.get('open_prediction'),
            duration=request.args.get('duration'),
            grade=request.args.get('grade'),
            sort_by=request.args.get('sort_by', 'score_desc'),
            page=request.args.get('page', 1, type=int),
            page_size=request.args.get('page_size', 20, type=int),
        )
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@notice_bp.route('/api/notice/detail/<content_hash>')
def notice_detail(content_hash):
    """公告详情（全部25字段）"""
    try:
        result = notice_analysis_service.get_notice_detail(content_hash)
        if result:
            return jsonify({'code': 0, 'message': 'success', 'data': result})
        return jsonify({'code': 404, 'message': '不存在', 'data': None}), 404
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@notice_bp.route('/api/notice/stats')
def notice_stats():
    """公告统计（向下兼容V2）"""
    try:
        date = request.args.get('date')
        result = notice_analysis_service.get_notice_stats(date)
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@notice_bp.route('/api/notice/top-signals')
def notice_top_signals():
    """顶级信号快览（4组合TopN）"""
    try:
        date = request.args.get('date')
        limit = request.args.get('limit', 5, type=int)
        result = notice_analysis_service.get_notice_top_signals(date, limit)
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@notice_bp.route('/api/notice/stats-v2')
def notice_stats_v2():
    """增强统计（评分档位+超短维度）"""
    try:
        date = request.args.get('date')
        result = notice_analysis_service.get_notice_stats_v2(date)
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@notice_bp.route('/api/notice/categories')
def notice_categories():
    """公告分类动态列表"""
    try:
        date = request.args.get('date')
        cats = notice_analysis_service.get_notice_categories(date)
        return jsonify({'code': 0, 'message': 'success', 'data': {'categories': cats}})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500
