"""领域分析API路由

提供领域分析相关的RESTful API端点：
    - GET /api/domain/list - 领域事件列表
    - GET /api/domain/detail/<hash> - 单条详情
    - GET /api/domain/stats - 统计信息
    - GET /api/domain/areas - 领域列表
    - GET /api/domain/hot-sectors - 热门板块
"""

from flask import Blueprint, request, jsonify

from gs2026.dashboard2.services import domain_analysis_service

domain_bp = Blueprint('domain', __name__)


@domain_bp.route('/api/domain/list')
def domain_list():
    """领域事件列表
    
    Query Params:
        date: 日期 YYYYMMDD（默认当天）
        main_area: 主领域筛选
        child_area: 子领域筛选
        search: 全文搜索（标题/描述/原因分析）
        type: 类型筛选 (利好/利空/中性)
        size: 大小筛选 (重大/大/中/小)
        min_score: 最低综合评分 (0-100)
        sector: 板块筛选
        concept: 概念筛选
        page: 页码（默认1）
        page_size: 每页条数（默认20）
        sort: 排序 (time/score，默认time)
    """
    try:
        date = request.args.get('date')
        main_area = request.args.get('main_area')
        child_area = request.args.get('child_area')
        search = request.args.get('search')
        news_type = request.args.get('type')
        news_size = request.args.get('size')
        min_score = request.args.get('min_score', 0, type=int)
        sector = request.args.get('sector')
        concept = request.args.get('concept')
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        sort_by = request.args.get('sort', 'time')
        
        result = domain_analysis_service.get_domain_list(
            date=date,
            main_area=main_area,
            child_area=child_area,
            search=search,
            news_type=news_type,
            news_size=news_size,
            min_score=min_score,
            sector=sector,
            concept=concept,
            page=page,
            page_size=page_size,
            sort_by=sort_by
        )
        
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': result
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@domain_bp.route('/api/domain/detail/<content_hash>')
def domain_detail(content_hash):
    """单条领域事件详情"""
    try:
        result = domain_analysis_service.get_domain_detail(content_hash)
        if result:
            return jsonify({
                'code': 0,
                'message': 'success',
                'data': result
            })
        else:
            return jsonify({
                'code': 404,
                'message': '领域事件不存在',
                'data': None
            }), 404
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@domain_bp.route('/api/domain/stats')
def domain_stats():
    """领域统计信息"""
    try:
        date = request.args.get('date')
        main_area = request.args.get('main_area')
        
        result = domain_analysis_service.get_domain_stats(date, main_area)
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': result
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@domain_bp.route('/api/domain/areas')
def domain_areas():
    """获取领域列表（主领域+子领域）"""
    try:
        result = domain_analysis_service.get_areas()
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': result
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@domain_bp.route('/api/domain/hot-sectors')
def domain_hot_sectors():
    """热门板块排行"""
    try:
        date = request.args.get('date')
        top = request.args.get('top', 10, type=int)
        
        result = domain_analysis_service.get_hot_sectors(date, top)
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': result
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500
