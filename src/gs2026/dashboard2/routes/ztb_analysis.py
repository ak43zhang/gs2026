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


@ztb_bp.route('/api/ztb/timestamps')
def get_ztb_timestamps():
    """
    获取涨停选股时间轴时间戳列表
    
    与数据监控完全一致:
    - Redis: monitor_gp_apqd_{date}:timestamps
    - MySQL: monitor_gp_apqd_{date}
    """
    try:
        date = request.args.get('date')
        if not date:
            return jsonify({'code': 400, 'message': '缺少date参数'}), 400
        
        timestamps = ztb_analysis_service.get_ztb_timestamps(date)
        
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': timestamps,
            'count': len(timestamps)
        })
        
    except Exception as e:
        logger.error(f"获取时间戳失败: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


@ztb_bp.route('/api/ztb/list-by-time')
def ztb_list_by_time():
    """
    获取指定时间点的涨停股票列表
    
    数据查询与数据监控完全一致:
    1. 先查Redis: monitor_gp_sssj_{date}:{time}
    2. Redis无: 查MySQL monitor_gp_sssj_{date} WHERE time={time}
    3. 筛选is_zt=1的股票
    """
    try:
        date = request.args.get('date')
        time_str = request.args.get('time')
        
        if not date or not time_str:
            return jsonify({
                'code': 400, 
                'message': '缺少date或time参数'
            }), 400
        
        result = ztb_analysis_service.get_ztb_list_by_time(date, time_str)
        
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': result
        })
        
    except Exception as e:
        logger.error(f"获取时间点涨停列表失败: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500
