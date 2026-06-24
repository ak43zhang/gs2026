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
    board = request.args.get('board', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    
    # 限制最大页大小（支持一天全部数据）
    if page_size > 500:
        page_size = 500
    if page_size < 1:
        page_size = 20
    if page < 1:
        page = 1

    engine = _get_engine()
    
    # 构建 WHERE 条件
    where_clauses = ["trading_date = :date"]
    params = {'date': target_date}
    
    if anomaly_type:
        where_clauses.append("anomaly_type = :type")
        params['type'] = anomaly_type
    if status:
        where_clauses.append("ai_status = :status")
        params['status'] = status
    if board == 'main_no_st':
        where_clauses.append("(stock_code LIKE '00%%' OR stock_code LIKE '60%%')")
        where_clauses.append("stock_name NOT LIKE '%%ST%%'")
    
    where_sql = " AND ".join(where_clauses)
    
    # 先重置超时状态（超过5分钟的processing/analyzed/correlating重置为pending）
    reset_sql = text(f"""
        UPDATE stock_anomaly 
        SET ai_status = 'pending', updated_at = NOW()
        WHERE {where_sql}
        AND ai_status IN ('processing', 'analyzed', 'correlating')
        AND TIMESTAMPDIFF(MINUTE, updated_at, NOW()) > 5
    """)
    
    # 先查总数
    count_sql = f"SELECT COUNT(*) FROM stock_anomaly WHERE {where_sql}"
    
    # 再分页查数据（SQL层LIMIT/OFFSET）
    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT id, trading_date, stock_code, stock_name, anomaly_type,
               anomaly_time, price, change_pct, continuous_zt,
               ai_analysis, ai_status,
               related_industries, related_concepts,
               pre_forecast_messages, forecast_match, forecast_note,
               mainline_names, correlation_context,
               created_at
        FROM stock_anomaly
        WHERE {where_sql}
        ORDER BY anomaly_time DESC
        LIMIT {page_size} OFFSET {offset}
    """

    with engine.connect() as conn:
        # 重置超时状态
        conn.execute(reset_sql, params)
        conn.commit()
        
        # 查询总数
        total = conn.execute(text(count_sql), params).scalar() or 0
        # 查询当前页数据
        result = conn.execute(text(data_sql), params)
        columns = list(result.keys())
        rows = result.fetchall()

    items = []
    for row in rows:
        item = dict(zip(columns, row))
        # 转换字段类型
        item['trading_date'] = str(item['trading_date'])
        # 格式化时间为 HH:MM:SS（处理 timedelta/time/字符串多种情况）
        raw_time = item.get('anomaly_time')
        if raw_time:
            try:
                from datetime import time, timedelta
                if isinstance(raw_time, time):
                    item['anomaly_time'] = f"{raw_time.hour:02d}:{raw_time.minute:02d}:{raw_time.second:02d}"
                elif isinstance(raw_time, timedelta):
                    total_sec = int(raw_time.total_seconds())
                    h = total_sec // 3600
                    m = (total_sec % 3600) // 60
                    s = total_sec % 60
                    item['anomaly_time'] = f"{h:02d}:{m:02d}:{s:02d}"
                else:
                    # 字符串，确保 HH:MM:SS
                    parts = str(raw_time).split(':')
                    if len(parts) >= 2:
                        item['anomaly_time'] = f"{int(parts[0]):02d}:{int(parts[1]):02d}:{parts[2] if len(parts) > 2 else '00'}"
            except Exception:
                item['anomaly_time'] = str(raw_time)
        else:
            item['anomaly_time'] = ''
        item['price'] = float(item['price']) if item['price'] else None
        item['change_pct'] = float(item['change_pct']) if item['change_pct'] else None
        item['created_at'] = str(item['created_at']) if item['created_at'] else None
        # 解析 JSON 字段
        for field in ('ai_analysis', 'related_industries', 'related_concepts', 'pre_forecast_messages', 'mainline_names'):
            val = item.get(field)
            if isinstance(val, str):
                try:
                    item[field] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    pass
        items.append(item)
    
    # 分页信息（已在SQL层完成分页）
    total_pages = (total + page_size - 1) // page_size
    
    return jsonify(
        success=True, 
        data=items, 
        count=len(items),
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
    
    # 重置超时状态
    reset_sql = text("""
        UPDATE stock_anomaly 
        SET ai_status = 'pending', updated_at = NOW()
        WHERE trading_date = :date
        AND ai_status IN ('processing', 'analyzed', 'correlating')
        AND TIMESTAMPDIFF(MINUTE, updated_at, NOW()) > 5
    """)

    sql = text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN ai_status = 'done' THEN 1 ELSE 0 END) as analyzed,
            SUM(CASE WHEN ai_status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN ai_status = 'processing' THEN 1 ELSE 0 END) as processing,
            SUM(CASE WHEN ai_status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN ai_status = 'analyzed' THEN 1 ELSE 0 END) as analyzed_status,
            SUM(CASE WHEN ai_status = 'correlating' THEN 1 ELSE 0 END) as correlating,
            SUM(CASE WHEN forecast_match = 'exact' THEN 1 ELSE 0 END) as match_exact,
            SUM(CASE WHEN forecast_match = 'partial' THEN 1 ELSE 0 END) as match_partial,
            SUM(CASE WHEN forecast_match = 'none' AND ai_status = 'done' THEN 1 ELSE 0 END) as match_none,
            SUM(CASE WHEN pre_forecast_messages IS NOT NULL THEN 1 ELSE 0 END) as watchlist_hit
        FROM stock_anomaly
        WHERE trading_date = :date
    """)

    with engine.connect() as conn:
        # 重置超时状态
        conn.execute(reset_sql, {'date': target_date})
        conn.commit()
        
        result = conn.execute(sql, {'date': target_date})
        row = result.fetchone()

    stats = {
        'total': int(row[0] or 0),
        'analyzed': int(row[1] or 0),
        'pending': int(row[2] or 0),
        'processing': int(row[3] or 0),
        'failed': int(row[4] or 0),
        'analyzed_status': int(row[5] or 0),
        'correlating': int(row[6] or 0),
        'match_exact': int(row[7] or 0),
        'match_partial': int(row[8] or 0),
        'match_none': int(row[9] or 0),
        'watchlist_hit': int(row[10] or 0),
    }

    return jsonify(success=True, data=stats)


@anomaly_bp.route('/api/anomaly/mainlines')
def anomaly_mainlines():
    """获取当天活跃市场主线列表
    
    Query params:
        date: 日期 YYYY-MM-DD（默认今天）
    """
    target_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    engine = _get_engine()

    sql = text("""
        SELECT mainline_id, mainline_name, mainline_reason, catalyst,
               related_stocks, confidence, stock_count,
               first_seen_time, last_updated_time, status
        FROM stock_anomaly_mainline
        WHERE trading_date = :date AND status = 'active'
        ORDER BY confidence DESC, stock_count DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(sql, {'date': target_date})
        columns = list(result.keys())
        rows = result.fetchall()

    items = []
    for row in rows:
        item = dict(zip(columns, row))
        # 解析 JSON 字段
        if isinstance(item.get('related_stocks'), str):
            try:
                item['related_stocks'] = json.loads(item['related_stocks'])
            except (json.JSONDecodeError, ValueError):
                item['related_stocks'] = []
        # 时间格式化
        item['first_seen_time'] = str(item['first_seen_time']) if item.get('first_seen_time') else None
        item['last_updated_time'] = str(item['last_updated_time']) if item.get('last_updated_time') else None
        items.append(item)

    return jsonify(success=True, data=items, count=len(items))


@anomaly_bp.route('/api/anomaly/potential', methods=['GET', 'POST'])
def get_potential_stocks():
    """获取潜在标的
    
    Query params (GET):
        date: 日期 YYYY-MM-DD（默认今天）
        time: 时间 HH:MM:SS（可选，复盘模式用）
    
    POST body (JSON):
        date: 日期
        time: 时间（复盘模式）
        replay: 1（复盘模式标记）
        mainlines: 主线列表（复盘模式使用前端传递的主线）
    
    POST: 手动触发重新挖掘
    """
    from datetime import date as dt_date
    
    if request.method == 'POST':
        data = request.get_json() or {}
        trading_date = data.get('date', dt_date.today().strftime('%Y-%m-%d'))
        target_time = data.get('time')
        is_replay = data.get('replay') == 1
        mainlines = data.get('mainlines', [])  # 前端传递的主线列表
        
        if is_replay and target_time:
            # 复盘模式：使用前端传递的主线列表
            from gs2026.analysis.worker.realtime.anomaly_potential import analyze_potential_with_mainlines
            potential = analyze_potential_with_mainlines(trading_date, target_time, mainlines)
            return jsonify(success=True, data=potential, mode='replay', target_time=target_time)
        else:
            # 实时模式：正常挖掘并保存
            from gs2026.analysis.worker.realtime.anomaly_potential import find_potential_stocks
            potential = find_potential_stocks(trading_date, trigger_type='manual')
            return jsonify(success=True, data=potential, trigger_type='manual')
    
    # GET: 查询已有结果
    trading_date = request.args.get('date', dt_date.today().strftime('%Y-%m-%d'))
    target_time = request.args.get('time')
    from gs2026.analysis.worker.realtime.anomaly_potential import get_potential_by_time
    potential = get_potential_by_time(trading_date, target_time)
    return jsonify(success=True, data=potential)


@anomaly_bp.route('/api/anomaly/potential/latest', methods=['GET'])
def get_potential_latest():
    """获取最新潜在标的（用于实时展示）"""
    from datetime import date as dt_date
    
    trading_date = request.args.get('date', dt_date.today().strftime('%Y-%m-%d'))
    
    from gs2026.analysis.worker.realtime.anomaly_potential import get_potential_by_time
    potential = get_potential_by_time(trading_date, None)  # None = 最新
    
    return jsonify(success=True, data=potential)


@anomaly_bp.route('/api/anomaly/potential/history', methods=['GET'])
def get_potential_history():
    """获取潜在标的挖掘历史时间点"""
    from datetime import date as dt_date
    
    trading_date = request.args.get('date', dt_date.today().strftime('%Y-%m-%d'))
    
    from gs2026.analysis.worker.realtime.anomaly_potential import get_potential_history
    history = get_potential_history(trading_date)
    
    return jsonify(success=True, data=history)
