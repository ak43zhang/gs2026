"""盘中异动 API 路由"""
import json
from datetime import date

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import create_engine, text

from gs2026.utils import config_util

anomaly_bp = Blueprint('anomaly', __name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        url = config_util.get_config('common.url')
        _engine = create_engine(url)
    return _engine


@anomaly_bp.route('/anomaly')
def anomaly_page():
    """盘中异动页面"""
    return render_template('anomaly.html')


@anomaly_bp.route('/api/anomaly/list')
def anomaly_list():
    """获取异动列表
    
    Query params:
        date: 日期 YYYY-MM-DD（默认今天）
        type: 异动类型（默认全部）
        status: AI状态（默认全部）
        page: 页码（默认1）
        page_size: 每页条数（默认20）
    """
    target_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    anomaly_type = request.args.get('type', '')
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    
    # 限制最大页大小
    if page_size > 100:
        page_size = 100
    if page_size < 1:
        page_size = 20
    if page < 1:
        page = 1

    engine = _get_engine()
    
    sql = """
        SELECT id, trading_date, stock_code, stock_name, anomaly_type,
               anomaly_time, price, change_pct, continuous_zt,
               ai_analysis, ai_status,
               related_industries, related_concepts,
               pre_forecast_messages, forecast_match, forecast_note,
               created_at
        FROM stock_anomaly
        WHERE trading_date = :date
    """
    params = {'date': target_date}
    
    if anomaly_type:
        sql += " AND anomaly_type = :type"
        params['type'] = anomaly_type
    if status:
        sql += " AND ai_status = :status"
        params['status'] = status
    
    sql += " ORDER BY anomaly_time DESC"

    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        columns = list(result.keys())
        rows = result.fetchall()

    items = []
    for row in rows:
        item = dict(zip(columns, row))
        # 转换字段类型
        item['trading_date'] = str(item['trading_date'])
        item['anomaly_time'] = str(item['anomaly_time'])
        item['price'] = float(item['price']) if item['price'] else None
        item['change_pct'] = float(item['change_pct']) if item['change_pct'] else None
        item['created_at'] = str(item['created_at']) if item['created_at'] else None
        # 解析 JSON 字段
        for field in ('ai_analysis', 'related_industries', 'related_concepts', 'pre_forecast_messages'):
            val = item.get(field)
            if isinstance(val, str):
                try:
                    item[field] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    pass
        items.append(item)
    
    # 分页
    total = len(items)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    paginated_items = items[start:end]
    
    return jsonify(
        success=True, 
        data=paginated_items, 
        count=len(paginated_items),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@anomaly_bp.route('/api/anomaly/stats')
def anomaly_stats():
    """获取异动统计
    
    Query params:
        date: 日期 YYYY-MM-DD（默认今天）
    """
    target_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    engine = _get_engine()

    sql = text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN ai_status = 'done' THEN 1 ELSE 0 END) as analyzed,
            SUM(CASE WHEN ai_status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN ai_status = 'processing' THEN 1 ELSE 0 END) as processing,
            SUM(CASE WHEN ai_status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN forecast_match = 'exact' THEN 1 ELSE 0 END) as match_exact,
            SUM(CASE WHEN forecast_match = 'partial' THEN 1 ELSE 0 END) as match_partial,
            SUM(CASE WHEN forecast_match = 'none' AND ai_status = 'done' THEN 1 ELSE 0 END) as match_none,
            SUM(CASE WHEN pre_forecast_messages IS NOT NULL THEN 1 ELSE 0 END) as watchlist_hit
        FROM stock_anomaly
        WHERE trading_date = :date
    """)

    with engine.connect() as conn:
        result = conn.execute(sql, {'date': target_date})
        row = result.fetchone()

    stats = {
        'total': int(row[0] or 0),
        'analyzed': int(row[1] or 0),
        'pending': int(row[2] or 0),
        'processing': int(row[3] or 0),
        'failed': int(row[4] or 0),
        'match_exact': int(row[5] or 0),
        'match_partial': int(row[6] or 0),
        'match_none': int(row[7] or 0),
        'watchlist_hit': int(row[8] or 0),
    }

    return jsonify(success=True, data=stats)
