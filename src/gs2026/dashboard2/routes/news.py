"""新闻中心 API 路由

路由列表:
    GET /news                     新闻中心页面
    GET /api/news/list          新闻列表（分页、筛选）
    GET /api/news/detail/<hash> 单条新闻详情
    GET /api/news/stats         当日统计数据
    GET /api/news/hot-sectors   热点板块排行
"""

from datetime import datetime
from flask import Blueprint, jsonify, request, render_template

from gs2026.dashboard2.services import news_service

news_bp = Blueprint('news', __name__)


@news_bp.route('/news')
def news_page():
    """新闻中心页面"""
    return render_template('news.html')


@news_bp.route('/api/news/list')
def news_list():
    """新闻列表

    Query Params:
        date: YYYYMMDD（与start_time/end_time互斥，优先使用date）
        start_time: 开始时间（格式：YYYY-MM-DD HH:MM:SS）
        end_time: 结束时间（格式：YYYY-MM-DD HH:MM:SS）
        type: 利好|利空|中性
        size: 重大|大|中|小
        sector: 板块名称
        search: 搜索关键词（标题+内容全文搜索）
        page: 页码（默认1）
        page_size: 每页条数（默认20，最大100）
        sort: time|score（默认time）
        min_score: 最低评分（默认0）
    """
    date = request.args.get('date')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    news_type = request.args.get('type')
    news_size = request.args.get('size')
    sector = request.args.get('sector')
    search = request.args.get('search', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    page_size = min(100, max(1, int(request.args.get('page_size', 20))))
    sort_by = request.args.get('sort', 'time')
    min_score = max(-32768, min(32767, int(request.args.get('min_score', 0))))

    result = news_service.get_news_list(
        date=date, start_time=start_time, end_time=end_time,
        news_type=news_type, news_size=news_size, sector=sector,
        search=search, page=page, page_size=page_size,
        sort_by=sort_by, min_score=min_score
    )
    return jsonify({'code': 0, 'message': 'success', 'data': result})


@news_bp.route('/api/news/detail/<content_hash>')
def news_detail(content_hash):
    """单条新闻详情"""
    detail = news_service.get_news_detail(content_hash)
    if detail is None:
        return jsonify({'error': '未找到该新闻'}), 404
    return jsonify(detail)


@news_bp.route('/api/news/stats')
def news_stats():
    """当日统计数据

    Query Params:
        date: YYYYMMDD（默认今天）
    """
    date = request.args.get('date', datetime.now().strftime('%Y%m%d'))
    stats = news_service.get_news_stats(date)
    return jsonify({'code': 0, 'message': 'success', 'data': stats})


@news_bp.route('/api/news/hot-sectors')
def hot_sectors():
    """热点板块排行

    Query Params:
        date: YYYYMMDD（默认今天）
        top: 返回条数（默认10）
    """
    date = request.args.get('date', datetime.now().strftime('%Y%m%d'))
    top_n = min(50, max(1, int(request.args.get('top', 10))))
    sectors = news_service.get_hot_sectors(date, top_n)
    return jsonify({'code': 0, 'message': 'success', 'data': sectors})
