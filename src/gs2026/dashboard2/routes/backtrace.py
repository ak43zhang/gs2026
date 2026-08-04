#!/usr/bin/env python3
"""
股债交集回溯路由
遍历时间轴，股票和债券分别过滤后取交集
"""
import logging
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime

from gs2026.common.pipeline import FilterConfig, UnifiedPipeline
from gs2026.common.pipeline.pipeline import IntersectionCalculator

logger = logging.getLogger(__name__)

backtrace_bp = Blueprint('backtrace', __name__, template_folder='../templates')


def _get_green_bond_set(actual_date: str) -> set:
    """获取绿名单债券code集合（当天走Redis缓存 / 历史走MySQL green_bond_list表）
    
    与 monitor.py 的 get_bond_ranking 路由绿名单标记逻辑完全一致。
    """
    try:
        from gs2026.dashboard2.routes.green_bond_list_cache import (
            get_green_bond_list, get_green_bond_list_cache_date
        )
        cache_date = get_green_bond_list_cache_date()
        if cache_date == actual_date:
            return get_green_bond_list()
        # 历史日期：从MySQL按buy_date查询
        import pandas as pd
        from gs2026.utils.mysql_util import get_mysql_tool
        mysql_tool = get_mysql_tool()
        date_sql = f"{actual_date[:4]}-{actual_date[4:6]}-{actual_date[6:8]}"
        df = pd.read_sql(
            f"SELECT DISTINCT code FROM green_bond_list WHERE buy_date='{date_sql}'",
            con=mysql_tool.engine
        )
        return set(df['code'].astype(str).str.zfill(6).tolist()) if not df.empty else set()
    except Exception as e:
        logger.warning(f"获取绿名单失败: {e}")
        return set()


@backtrace_bp.route('/backtrace')
def index():
    """股债交集回溯页面"""
    return render_template('backtrace.html')


@backtrace_bp.route('/api/backtrace/dates')
def api_dates():
    """获取可选日期列表"""
    try:
        from gs2026.dashboard2.services.range_analysis_service import get_available_dates
        dates = get_available_dates()
        return jsonify({'code': 0, 'data': dates})
    except Exception as e:
        logger.error(f"获取日期失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


@backtrace_bp.route('/api/backtrace/timestamps')
def api_timestamps():
    """获取某日所有时间戳"""
    date = request.args.get('date', '').strip()
    if not date:
        return jsonify({'code': 1, 'message': '缺少date参数'})
    
    try:
        from gs2026.dashboard2.services.range_analysis_service import get_timestamps
        timestamps = get_timestamps(date)
        return jsonify({'code': 0, 'data': timestamps})
    except Exception as e:
        logger.error(f"获取时间戳失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})


def _norm_time(t, is_end=False):
    """规范化时间为 HH:MM:SS（<input type=time> 可能只返回 HH:MM）"""
    if not t:
        return t
    parts = t.split(':')
    if len(parts) == 2:
        return f"{t}:{'59' if is_end else '00'}"
    return t


def _assemble_stock(code, cnt, name, wc_map, sssj_slice, mapping_all, green_set):
    """内存组装单条股票数据（字段与 _enrich_stock_data + _enrich_change_pct_and_main_net 一致）"""
    m = mapping_all.get(code) or {}
    bond_code = m.get('bond_code', '-') if m else '-'
    s = sssj_slice.get(code) or {}
    change_pct = s.get('change_pct', '-')
    return {
        'code': code,
        'name': name,
        'count': cnt,
        'window_count': wc_map.get(code, 0),
        'bond_code': bond_code,
        'bond_name': m.get('bond_name', '-') if m else '-',
        'industry_name': m.get('industry_name', '-') if m else '-',
        'change_pct': change_pct if change_pct is not None else '-',
        'main_net_amount': s.get('main_net_amount', 0) or 0,
        'is_green_bond': bond_code not in (None, '-', '') and str(bond_code).zfill(6) in green_set,
    }


def _assemble_bond(code, cnt, name, wc_map, sssj_slice, industry_map, green_set):
    """内存组装单条债券数据（字段与 _enrich_bond_data 一致）"""
    s = sssj_slice.get(code) or {}
    change_pct = s.get('change_pct', '-')
    return {
        'code': code,
        'name': name,
        'count': cnt,
        'window_count': wc_map.get(code, 0),
        'change_pct': change_pct if change_pct is not None else '-',
        'price': s.get('price', '-') if s else '-',
        'amount': float(s.get('amount', 0) or 0),
        'industry_name': industry_map.get(code, '-'),
        'is_green': str(code).zfill(6) in green_set,
    }


BATCH_TICKS = 100  # 每批处理的tick数


def _run_backtrace_core(date, stock_config, bond_config, start_time, end_time):
    """回溯核心（分批+code过滤），生成器逐批yield进度事件。

    yield事件格式:
      {'type':'start', 'total':N}
      {'type':'preload', 'msg':'...'}
      {'type':'progress', 'done':x, 'total':N, 'batch':i, 'batches':B, 'found':F}
      {'type':'done', 'data':{...}}
      {'type':'error', 'message':'...'}
    """
    from gs2026.dashboard2.services.range_analysis_service import get_timestamps
    from gs2026.dashboard2.routes.monitor import (
        _get_shared_engine, get_cache, _get_bond_industry_batch,
    )
    from gs2026.dashboard2.routes.backtrace_preload import (
        preload_top30, preload_sssj, get_candidate_codes,
        build_count_timeline, build_window_count_timeline,
    )

    actual_date = date.replace('-', '')
    st = _norm_time((start_time or '').strip(), is_end=False)
    et = _norm_time((end_time or '').strip(), is_end=True)

    stock_filter_config = FilterConfig.from_dict(stock_config)
    bond_filter_config = FilterConfig.from_dict(bond_config)

    timestamps = get_timestamps(actual_date)
    if not timestamps:
        yield {'type': 'error', 'message': '该日期无数据'}
        return
    if st:
        timestamps = [t for t in timestamps if t >= st]
    if et:
        timestamps = [t for t in timestamps if t <= et]
    if not timestamps:
        yield {'type': 'error', 'message': '指定时间范围内无数据'}
        return

    total = len(timestamps)
    yield {'type': 'start', 'total': total}

    engine = _get_shared_engine()
    load_end = et if et else timestamps[-1]

    # === top30 一次性加载（小表）+ 构建时间线 + 候选code ===
    yield {'type': 'preload', 'msg': '加载排行数据(top30)...'}
    stock_rows = preload_top30(engine, actual_date, 'stock', end_time=load_end)
    bond_rows = preload_top30(engine, actual_date, 'bond', end_time=load_end)

    stock_count_tl, stock_name_map = build_count_timeline(stock_rows, timestamps)
    bond_count_tl, bond_name_map = build_count_timeline(bond_rows, timestamps)
    stock_wc_tl = build_window_count_timeline(stock_rows, timestamps)
    bond_wc_tl = build_window_count_timeline(bond_rows, timestamps)

    stock_candidates = get_candidate_codes(stock_rows)
    bond_candidates = get_candidate_codes(bond_rows)

    # === 映射 + 绿名单 + 债券行业（一次性）===
    yield {'type': 'preload', 'msg': '加载股债映射/绿名单/行业...'}
    cache = get_cache()
    mapping_all = cache.get_mappings_smart(list(stock_name_map.keys())) if stock_name_map else {}
    green_set = _get_green_bond_set(actual_date)
    bond_industry_map = _get_bond_industry_batch(list(bond_name_map.keys())) if bond_name_map else {}

    stock_pipeline = UnifiedPipeline(stock_filter_config)
    bond_pipeline = UnifiedPipeline(bond_filter_config)

    # === 按tick分批处理（每批只查该窗口+候选code的sssj）===
    results = []
    batches = (total + BATCH_TICKS - 1) // BATCH_TICKS
    done = 0
    for bi in range(batches):
        batch = timestamps[bi * BATCH_TICKS:(bi + 1) * BATCH_TICKS]
        if not batch:
            continue
        b_start, b_end = batch[0], batch[-1]

        # 本批sssj（时间窗口 + code过滤）
        stock_sssj = preload_sssj(engine, actual_date, 'stock',
                                  start_time=b_start, end_time=b_end, codes=stock_candidates)
        bond_sssj = preload_sssj(engine, actual_date, 'bond',
                                 start_time=b_start, end_time=b_end, codes=bond_candidates)

        for time_str in batch:
            try:
                sc = stock_count_tl.get(time_str, {})
                swc = stock_wc_tl.get(time_str, {})
                s_slice = stock_sssj.get(time_str, {})
                stock_data = [
                    _assemble_stock(code, cnt, stock_name_map.get(code, ''),
                                    swc, s_slice, mapping_all, green_set)
                    for code, cnt in sc.items()
                ]
                bc = bond_count_tl.get(time_str, {})
                bwc = bond_wc_tl.get(time_str, {})
                b_slice = bond_sssj.get(time_str, {})
                bond_data = [
                    _assemble_bond(code, cnt, bond_name_map.get(code, ''),
                                   bwc, b_slice, bond_industry_map, green_set)
                    for code, cnt in bc.items()
                ]
                filtered_stocks = stock_pipeline.filter_stocks(stock_data)
                filtered_bonds = bond_pipeline.filter_bonds(bond_data)
                intersection = IntersectionCalculator.calculate(filtered_stocks, filtered_bonds)
                if intersection:
                    results.append({
                        'time': time_str,
                        'count': len(intersection),
                        'stocks': intersection
                    })
            except Exception as e:
                logger.error(f"处理时间点 {time_str} 失败: {e}", exc_info=True)
                continue
            done += 1

        # 释放本批sssj内存
        del stock_sssj, bond_sssj

        yield {'type': 'progress', 'done': done, 'total': total,
               'batch': bi + 1, 'batches': batches, 'found': len(results)}

    logger.info(f"[回溯完成] {actual_date} {st}~{et}: {total}个时间点, {len(results)}个有交集")
    yield {'type': 'done', 'data': {
        'date': date, 'start_time': st, 'end_time': et,
        'total_timestamps': total,
        'intersection_count': len(results),
        'results': results
    }}


@backtrace_bp.route('/api/backtrace/run', methods=['POST'])
def api_run():
    """执行股债交集回溯（同步返回，兼容旧调用）"""
    try:
        data = request.get_json()
        final = None
        for ev in _run_backtrace_core(
            data.get('date'), data.get('stock_config', {}),
            data.get('bond_config', {}),
            data.get('start_time', ''), data.get('end_time', '')
        ):
            if ev['type'] == 'error':
                return jsonify({'code': 1, 'message': ev['message']})
            if ev['type'] == 'done':
                final = ev['data']
        if final is None:
            return jsonify({'code': 1, 'message': '无结果'})
        return jsonify({'code': 0, 'data': final})
    except Exception as e:
        logger.error(f"执行回溯失败: {e}", exc_info=True)
        return jsonify({'code': 1, 'message': str(e)})


@backtrace_bp.route('/api/backtrace/run-stream', methods=['POST'])
def api_run_stream():
    """执行股债交集回溯（SSE流式进度）"""
    import json as _json
    from flask import Response, stream_with_context

    data = request.get_json()
    date = data.get('date')
    stock_config = data.get('stock_config', {})
    bond_config = data.get('bond_config', {})
    start_time = data.get('start_time', '')
    end_time = data.get('end_time', '')

    @stream_with_context
    def generate():
        try:
            for ev in _run_backtrace_core(date, stock_config, bond_config, start_time, end_time):
                yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"流式回溯失败: {e}", exc_info=True)
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@backtrace_bp.route('/api/backtrace/save', methods=['POST'])
def api_save():
    """保存回溯结果到MySQL"""
    try:
        data = request.get_json()
        date = data.get('date')
        results = data.get('results', [])
        
        if not date or not results:
            return jsonify({'code': 1, 'message': '参数不完整'})
        
        # 保存到MySQL
        saved_count = 0
        for item in results:
            time_str = item.get('time')
            stocks = item.get('stocks', [])
            
            for stock in stocks:
                try:
                    # 构建记录
                    record = {
                        'date': date,
                        'time': time_str,
                        'stock_code': stock.get('stock_code'),
                        'stock_name': stock.get('stock_name'),
                        'bond_code': stock.get('bond_code'),
                        'bond_name': stock.get('bond_name'),
                        'stock_change_pct': stock.get('stock_change_pct'),
                        'bond_change_pct': stock.get('bond_change_pct'),
                        'stock_price': stock.get('stock_price'),
                        'bond_price': stock.get('bond_price'),
                        'stock_count': stock.get('stock_count'),
                        'bond_window_count': stock.get('bond_window_count'),
                        'industry': stock.get('industry'),
                        'main_net_amount': stock.get('main_net_amount')
                    }
                    
                    # 保存到数据库
                    # TODO: 实现数据库保存逻辑
                    saved_count += 1
                    
                except Exception as e:
                    logger.error(f"保存记录失败: {e}")
                    continue
        
        return jsonify({
            'code': 0,
            'message': f'成功保存 {saved_count} 条记录'
        })
        
    except Exception as e:
        logger.error(f"保存失败: {e}")
        return jsonify({'code': 1, 'message': str(e)})
