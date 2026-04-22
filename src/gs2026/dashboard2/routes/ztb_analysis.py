"""涨停分析API路由"""

from flask import Blueprint, request, jsonify

from gs2026.dashboard2.services import ztb_analysis_service

ztb_bp = Blueprint('ztb', __name__)


@ztb_bp.route('/api/ztb/list')
def ztb_list():
    """涨停列表"""
    try:
        date = request.args.get('date')
        stock_name = request.args.get('stock_name')
        stock_code = request.args.get('stock_code')
        sector = request.args.get('sector')
        concept = request.args.get('concept')
        zt_time_range = request.args.get('zt_time_range')
        has_expect = request.args.get('has_expect', type=int)
        continuity = request.args.get('continuity', type=int)
        market_filter = request.args.get('market_filter', 'all')
        cross_date = request.args.get('cross_date', type=int)  # 新增：跨日期查询标识
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        
        result = ztb_analysis_service.get_ztb_list(
            date=date,
            stock_name=stock_name,
            stock_code=stock_code,
            sector=sector,
            concept=concept,
            zt_time_range=zt_time_range,
            has_expect=has_expect,
            continuity=continuity,
            market_filter=market_filter,
            cross_date=cross_date,  # 传递新参数
            page=page,
            page_size=page_size
        )
        
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@ztb_bp.route('/api/ztb/detail/<content_hash>')
def ztb_detail(content_hash):
    """涨停详情"""
    try:
        date = request.args.get('date')  # 添加日期参数用于确定表名
        result = ztb_analysis_service.get_ztb_detail(content_hash, date)
        if result:
            return jsonify({'code': 0, 'message': 'success', 'data': result})
        return jsonify({'code': 404, 'message': '不存在', 'data': None}), 404
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@ztb_bp.route('/api/ztb/stats')
def ztb_stats():
    """涨停统计"""
    try:
        date = request.args.get('date')
        result = ztb_analysis_service.get_ztb_stats(date)
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500


@ztb_bp.route('/api/ztb/hot-sectors')
def ztb_hot_sectors():
    """热门板块"""
    try:
        date = request.args.get('date')
        top = request.args.get('top', 10, type=int)
        result = ztb_analysis_service.get_hot_sectors(date, top)
        return jsonify({'code': 0, 'message': 'success', 'data': result})
    except Exception as e:
        return jsonify({'code': 500, 'message': str(e), 'data': None}), 500
