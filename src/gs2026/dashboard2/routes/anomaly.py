"""盘中异动 API 路由"""
import json
import time as _time
from datetime import date, time, timedelta

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import create_engine, text

from gs2026.utils import config_util

anomaly_bp = Blueprint('anomaly', __name__)

_engine = None
_last_reset_time = 0  # 上次重置超时状态的时间戳


def _get_engine():
    global _engine
    if _engine is None:
        url = config_util.get_config('common.url')
        _engine = create_engine(url)
    return _engine


@anomaly_bp.route('/api/anomaly/latest-trading-date')
def get_latest_trading_date():
    """获取最近的交易日（如果今天不是交易日则返回上一个交易日）"""
    engine = _get_engine()
    today = date.today().strftime('%Y-%m-%d')
    sql = text(
        "SELECT trade_date FROM data_jyrl "
        "WHERE trade_date <= :today AND trade_status = '1' "
        "ORDER BY trade_date DESC LIMIT 1"
    )
    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {'today': today})
            row = result.fetchone()
        trading_date = str(row[0]) if row else today
        is_today = (trading_date == today)
        return jsonify({'success': True, 'date': trading_date, 'is_today': is_today})
    except Exception as e:
        return jsonify({'success': True, 'date': today, 'is_today': True})


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
    where_clauses = ["trading_date = :date", "stock_name NOT LIKE '%ST%'"]
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
    
    # 先重置超时状态（每5分钟执行一次，避免每次请求都写数据库）
    # 超过5分钟的 processing/analyzed/correlating 重置为 pending
    # failed 状态也重置为 pending（让它重新分析）
    global _last_reset_time
    now = _time.time()
    if now - _last_reset_time > 300:  # 5分钟
        reset_sql = text(f"""
            UPDATE stock_anomaly 
            SET ai_status = 'pending', updated_at = NOW()
            WHERE {where_sql}
            AND (
                (ai_status IN ('processing', 'analyzed', 'correlating') AND TIMESTAMPDIFF(MINUTE, updated_at, NOW()) > 5)
                OR ai_status = 'failed'
            )
        """)
        with engine.connect() as conn:
            conn.execute(reset_sql, params)
            conn.commit()
        _last_reset_time = now
    
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
               mainline_names,
               created_at
        FROM stock_anomaly
        WHERE {where_sql}
        ORDER BY anomaly_time DESC
        LIMIT {page_size} OFFSET {offset}
    """

    with engine.connect() as conn:
        t1 = _time.time()
        # 查询总数
        total = conn.execute(text(count_sql), params).scalar() or 0
        t2 = _time.time()
        # 查询当前页数据
        result = conn.execute(text(data_sql), params)
        columns = list(result.keys())
        rows = result.fetchall()
        t3 = _time.time()

    items = []
    for row in rows:
        item = dict(zip(columns, row))
        # 转换字段类型
        item['trading_date'] = str(item['trading_date'])
        # 格式化时间为 HH:MM:SS（处理 timedelta/time/字符串多种情况）
        raw_time = item.get('anomaly_time')
        if raw_time:
            try:
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
    t4 = _time.time()

    total_elapsed = t4 - t1
    from loguru import logger
    if total_elapsed > 1.5:
        logger.warning(f"[anomaly/list perf] count={t2-t1:.3f}s data={t3-t2:.3f}s python={t4-t3:.3f}s rows={len(rows)} total={total_elapsed:.3f}s")
    else:
        logger.debug(f"[anomaly/list perf] count={t2-t1:.3f}s data={t3-t2:.3f}s python={t4-t3:.3f}s rows={len(rows)} total={total_elapsed:.3f}s")
    
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
          AND stock_name NOT LIKE '%ST%'
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
               first_seen_time, last_updated_time, status,
               mainline_summary, synthesis_level, synthesis_time
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
        if isinstance(item.get('mainline_summary'), str):
            try:
                item['mainline_summary'] = json.loads(item['mainline_summary'])
            except (json.JSONDecodeError, ValueError):
                item['mainline_summary'] = None
        # 时间格式化
        item['first_seen_time'] = str(item['first_seen_time']) if item.get('first_seen_time') else None
        item['last_updated_time'] = str(item['last_updated_time']) if item.get('last_updated_time') else None
        item['synthesis_time'] = str(item['synthesis_time']) if item.get('synthesis_time') else None
        items.append(item)

    return jsonify(success=True, data=items, count=len(items))


@anomaly_bp.route('/api/anomaly/potential', methods=['GET', 'POST'])
def get_potential_stocks():
    """获取潜在标的
    
    Query params (GET):
        date: 日期 YYYY-MM-DD（默认今天）
        time: 时间 HH:MM:SS（可选，复盘模式用）
        replay: 是否复盘模式 '1' | '0'（默认'0'）
    
    POST body (JSON):
        date: 日期
        time: 时间（复盘模式）
        replay: 1（复盘模式标记）
        mainlines: 主线列表（复盘模式使用前端传递的主线）
        async: 1（异步模式，立即返回，后台执行）
    
    POST: 手动触发重新挖掘（实时或复盘）
    GET: 查询已有结果（支持复盘时间点）
    """
    from datetime import date as dt_date
    import threading
    
    if request.method == 'POST':
        data = request.get_json() or {}
        trading_date = data.get('date', dt_date.today().strftime('%Y-%m-%d'))
        target_time = data.get('time')
        is_replay = data.get('replay') == 1
        mainlines = data.get('mainlines', [])  # 前端传递的主线列表
        is_async = data.get('async') == 1  # 是否异步执行
        
        if is_async:
            # 异步模式：启动后台线程执行，立即返回
            def async_analyze():
                try:
                    if is_replay and target_time and mainlines:
                        from gs2026.analysis.worker.realtime.anomaly_potential import analyze_potential_with_mainlines
                        analyze_potential_with_mainlines(trading_date, target_time, mainlines)
                    else:
                        from gs2026.analysis.worker.realtime.anomaly_potential import find_potential_stocks
                        find_potential_stocks(trading_date, trigger_type='manual')
                except Exception as e:
                    logger.error(f"[异步潜在标的分析] 失败: {e}")
            
            thread = threading.Thread(target=async_analyze)
            thread.daemon = True
            thread.start()
            
            return jsonify(success=True, message='分析任务已启动，请稍后刷新查看结果', is_async=True)
        
        # 同步模式（默认）
        if is_replay and target_time and mainlines:
            # 复盘模式：使用前端传递的主线列表，保存结果
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
    is_replay = request.args.get('replay') == '1'
    
    from gs2026.analysis.worker.realtime.anomaly_potential import get_potential_by_time
    potential = get_potential_by_time(trading_date, target_time, is_replay)
    return jsonify(success=True, data=potential, is_replay=is_replay)


@anomaly_bp.route('/api/anomaly/potential/latest', methods=['GET'])
def get_potential_latest():
    """获取最新潜在标的（用于实时展示）"""
    from datetime import date as dt_date
    
    trading_date = request.args.get('date', dt_date.today().strftime('%Y-%m-%d'))
    
    from gs2026.analysis.worker.realtime.anomaly_potential import get_potential_by_time
    potential = get_potential_by_time(trading_date, None, False)  # None = 最新，False = 非复盘
    
    return jsonify(success=True, data=potential)


@anomaly_bp.route('/api/anomaly/potential/replay-times', methods=['GET'])
def get_potential_replay_times():
    """获取已保存的复盘时间点列表"""
    from datetime import date as dt_date
    
    trading_date = request.args.get('date', dt_date.today().strftime('%Y-%m-%d'))
    
    from gs2026.analysis.worker.realtime.anomaly_potential import get_replay_times
    times = get_replay_times(trading_date)
    
    return jsonify(success=True, data=times)


@anomaly_bp.route('/api/anomaly/potential/history', methods=['GET'])
def get_potential_history():
    """获取潜在标的挖掘历史时间点"""
    from datetime import date as dt_date
    
    trading_date = request.args.get('date', dt_date.today().strftime('%Y-%m-%d'))
    
    from gs2026.analysis.worker.realtime.anomaly_potential import get_potential_history
    history = get_potential_history(trading_date)
    
    return jsonify(success=True, data=history)


@anomaly_bp.route('/api/anomaly/bond/discover')
def discover_mainline_bonds():
    """主线可转债挖掘：从主线→行业→同行业未涨停股票→可转债"""
    target_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    target_time = request.args.get('target_time', '')  # 复盘模式：HH:MM:SS

    engine = _get_engine()

    with engine.connect() as conn:
        # 1. 获取当日主线股票（支持复盘时间过滤）
        time_filter = ""
        if target_time:
            time_filter = f" AND anomaly_time <= '{target_time}'"

        mainline_rows = conn.execute(text(
            f"SELECT stock_code, stock_name, mainline_names "
            f"FROM stock_anomaly "
            f"WHERE trading_date = :date AND ai_status = 'done' "
            f"AND mainline_names IS NOT NULL AND mainline_names != '[\"独立个股\"]' "
            f"AND stock_name NOT LIKE '%ST%'"
            f"{time_filter}"
        ), {'date': target_date}).fetchall()

        if not mainline_rows:
            return jsonify(code=0, data=[])

        # 收集主线股票代码和主线映射
        stock_mainline_map = {}
        for row in mainline_rows:
            code = row[0]
            ml_raw = row[2]
            try:
                ml_list = json.loads(ml_raw) if isinstance(ml_raw, str) else ml_raw
            except (json.JSONDecodeError, ValueError):
                ml_list = []
            ml_list = [m for m in ml_list if m != '独立个股']
            if ml_list:
                stock_mainline_map[code] = ml_list

        if not stock_mainline_map:
            return jsonify(code=0, data=[])

        # 2. 获取这些股票的行业
        placeholders = ','.join([f"'{c}'" for c in stock_mainline_map.keys()])
        industry_rows = conn.execute(text(
            f"SELECT stock_code, code, name "
            f"FROM data_industry_code_component_ths "
            f"WHERE stock_code IN ({placeholders})"
        )).fetchall()

        # 建立 主线→行业 映射
        mainline_industries = {}
        for row in industry_rows:
            s_code, ind_code, ind_name = row
            if s_code in stock_mainline_map:
                for ml in stock_mainline_map[s_code]:
                    if ml not in mainline_industries:
                        mainline_industries[ml] = set()
                    mainline_industries[ml].add((ind_code, ind_name))

        if not mainline_industries:
            return jsonify(code=0, data=[])

        # 3. 获取这些行业中所有股票
        all_ind_codes = set()
        for inds in mainline_industries.values():
            for code, name in inds:
                all_ind_codes.add(code)

        ind_placeholders = ','.join([f"'{c}'" for c in all_ind_codes])
        all_ind_stocks = conn.execute(text(
            f"SELECT stock_code, short_name, code, name "
            f"FROM data_industry_code_component_ths "
            f"WHERE code IN ({ind_placeholders})"
        )).fetchall()

        # 4. 排除今天已涨停的
        zt_rows = conn.execute(text(
            "SELECT stock_code FROM stock_anomaly WHERE trading_date = :date"
        ), {'date': target_date}).fetchall()
        zt_codes = set(r[0] for r in zt_rows)

        candidates = {}
        for row in all_ind_stocks:
            code, name, ind_code, ind_name = row
            if code not in candidates:
                candidates[code] = {'name': name, 'mainlines': set(), 'is_zt': code in zt_codes}
            for ml, inds in mainline_industries.items():
                if (ind_code, ind_name) in inds:
                    candidates[code]['mainlines'].add(ml)

        # 5. 匹配可转债（排除已公告强赎、溢价率>100%）
        bond_rows = conn.execute(text(
            "SELECT `代码`,`名称`,`现价`,`正股代码`,`正股名称`,"
            "`转股价`,`正股价`,`剩余规模`,`强赎状态` "
            "FROM data_bond_qs_jsl "
            "WHERE `现价` IS NOT NULL AND `现价` > 0 "
            "AND (`强赎状态` IS NULL OR `强赎状态` = '' OR `强赎状态` NOT LIKE '%已公告强赎%')"
        )).fetchall()

        bond_map = {}
        for b in bond_rows:
            if b[3]:
                bond_map[b[3]] = {
                    'bond_code': b[0], 'bond_name': b[1], 'bond_price': float(b[2]) if b[2] else 0,
                    'stock_name': b[4],
                    'convert_price': float(b[5]) if b[5] else 0,
                    'stock_price': float(b[6]) if b[6] else 0,
                    'remaining': float(b[7]) if b[7] else 0,
                    'redeem_status': b[8] or ''
                }

        # 6. 匹配结果
        results = []
        for code, info in candidates.items():
            if code not in bond_map:
                continue
            bond = bond_map[code]
            # 计算溢价率
            premium = 0
            if bond['stock_price'] and bond['convert_price']:
                convert_value = bond['stock_price'] / bond['convert_price'] * 100
                premium = round((bond['bond_price'] / convert_value - 1) * 100, 1) if convert_value else 0

            if premium > 150:
                continue  # 排除超高溢价（>150%）

            ml_list = sorted(info['mainlines'])
            results.append({
                'bond_code': bond['bond_code'],
                'bond_name': bond['bond_name'],
                'bond_price': bond['bond_price'],
                'stock_code': code,
                'stock_name': info['name'],
                'convert_price': bond['convert_price'],
                'stock_price': bond['stock_price'],
                'premium_rate': premium,
                'remaining': bond['remaining'],
                'redeem_status': bond['redeem_status'],
                'mainline_count': len(ml_list),
                'mainlines': ml_list,
                'is_zt': info['is_zt']
            })

        # 7. 排序：主线数降序 → is_zt降序(涨停优先) → 溢价率升序 → 剩余规模降序
        results.sort(key=lambda x: (-x['mainline_count'], -int(x['is_zt']), x['premium_rate'], -x['remaining']))

    return jsonify(code=0, data=results)
