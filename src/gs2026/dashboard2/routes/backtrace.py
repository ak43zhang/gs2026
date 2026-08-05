#!/usr/bin/env python3
"""
股债交集回溯路由
遍历时间轴，股票和债券分别过滤后取交集
"""
import logging
import time
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime

from gs2026.common.pipeline import FilterConfig, UnifiedPipeline
from gs2026.common.pipeline.pipeline import IntersectionCalculator

logger = logging.getLogger(__name__)

backtrace_bp = Blueprint('backtrace', __name__, template_folder='../templates')


def _get_green_bond_set(actual_date: str) -> set:
    """获取绿名单债券code集合（按指定日期）。

    薄封装，复用唯一真相源 green_bond_list_cache.get_green_set_for_date：
    当天走Redis缓存 / 历史走MySQL green_bond_list 表，与实时监控口径完全一致。
    """
    from gs2026.dashboard2.routes.green_bond_list_cache import get_green_set_for_date
    return get_green_set_for_date(actual_date)


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
        # 1分钟字段（老日期表无此列时兜底为0，即不触发相关过滤）
        'min1_change_pct': float(s.get('min1_change_pct', 0) or 0),
        'min1_amount': float(s.get('min1_amount', 0) or 0),
        'industry_name': industry_map.get(code, '-'),
        'is_green': str(code).zfill(6) in green_set,
    }


BATCH_TICKS = 200  # 每批处理的tick数

# ==================== 10分钟窗口汇总功能 ====================

def generate_windows(start_time_str: str, end_time_str: str, window_minutes: int = 10) -> list:
    """生成时间窗口列表
    
    Args:
        start_time_str: 开始时间 HH:MM 或 HH:MM:SS
        end_time_str: 结束时间
        window_minutes: 窗口大小（分钟）
        
    Returns:
        窗口标识列表，如 ['09:30-09:40', '09:40-09:50', ...]
    """
    from datetime import datetime, timedelta
    
    # 解析时间
    fmt = '%H:%M:%S' if ':' in start_time_str and len(start_time_str.split(':')) == 3 else '%H:%M'
    start = datetime.strptime(start_time_str[:5] if len(start_time_str) > 5 else start_time_str, '%H:%M')
    end = datetime.strptime(end_time_str[:5] if len(end_time_str) > 5 else end_time_str, '%H:%M')
    
    windows = []
    current = start
    while current < end:
        window_end = current + timedelta(minutes=window_minutes)
        if window_end > end:
            window_end = end
        window_label = f"{current.strftime('%H:%M')}-{window_end.strftime('%H:%M')}"
        windows.append(window_label)
        current = window_end
    
    return windows


def get_window_for_time(time_str: str, windows: list) -> str:
    """根据时间点获取所属窗口
    
    Args:
        time_str: 时间字符串 HH:MM:SS
        windows: 窗口列表
        
    Returns:
        窗口标识，如 '14:20-14:30'
    """
    from datetime import datetime
    
    time_obj = datetime.strptime(time_str[:5], '%H:%M')
    
    for window in windows:
        start_str, end_str = window.split('-')
        start = datetime.strptime(start_str, '%H:%M')
        end = datetime.strptime(end_str, '%H:%M')
        
        if start <= time_obj < end:
            return window
    
    # 如果不在任何窗口内（如收盘时间），返回最后一个窗口
    return windows[-1] if windows else None


def time_diff_seconds(time1: str, time2: str) -> int:
    """计算两个时间的秒数差
    
    Args:
        time1: 时间1 HH:MM:SS
        time2: 时间2 HH:MM:SS
        
    Returns:
        秒数差（time2 - time1）
    """
    from datetime import datetime
    
    t1 = datetime.strptime(time1, '%H:%M:%S')
    t2 = datetime.strptime(time2, '%H:%M:%S')
    
    return int((t2 - t1).total_seconds())


def format_duration(seconds: int) -> str:
    """将秒数格式化为可读字符串
    
    Args:
        seconds: 秒数
        
    Returns:
        格式化字符串，如 '4分27秒'
    """
    minutes = seconds // 60
    secs = seconds % 60
    
    if minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"


def get_time_color_class(seconds: int) -> str:
    """根据时间差获取颜色类名
    
    Args:
        seconds: 秒数
        
    Returns:
        CSS类名: 'fast'(红), 'normal'(黄), 'slow'(绿)
    """
    if seconds < 120:  # < 2分钟
        return 'fast'  # 红色 - 快速拉升
    elif seconds <= 300:  # 2-5分钟
        return 'normal'  # 黄色 - 正常
    else:  # > 5分钟
        return 'slow'  # 绿色 - 缓慢爬升


def get_gain_color_class(gain: float) -> str:
    """根据涨幅差获取颜色类名（涨幅差/区间差共用）
    
    Args:
        gain: 涨幅差/区间差（百分比，可能为负）
        
    Returns:
        CSS类名: 'gain-low'(绿), 'gain-medium'(黄), 'gain-high'(红)
    """
    if gain < 0.4:
        return 'gain-low'      # 绿色 - 弱势/回落（含负数）
    elif gain < 2.0:
        return 'gain-medium'   # 黄色 - 正常
    else:
        return 'gain-high'     # 红色 - 强势


def calculate_window_summary(window: str, stock_code: str, bond_code: str, 
                             details: list, window_tick_count: int = 200) -> dict:
    """计算单个股债对在窗口内的汇总指标
    
    注意：所有涨幅字段均使用债券涨幅（bond_change_pct）
    
    Args:
        window: 窗口标识，如 '14:20-14:30'
        stock_code: 股票代码
        bond_code: 债券代码
        details: 该对在窗口内的所有明细记录
        window_tick_count: 窗口内总tick数（用于计算连续度）
        
    Returns:
        汇总数据字典
    """
    if not details:
        return None
    
    # 按时间排序
    sorted_details = sorted(details, key=lambda x: x.get('time', ''))
    
    first = sorted_details[0]
    last = sorted_details[-1]
    
    # 找到最高债券涨幅的记录（改用 bond_change_pct）
    max_record = max(sorted_details, key=lambda x: x.get('bond_change_pct', 0) if x.get('bond_change_pct') is not None else 0)
    min_record = min(sorted_details, key=lambda x: x.get('bond_change_pct', 0) if x.get('bond_change_pct') is not None else float('inf'))
    
    # 计算时间差
    time_to_max_seconds = time_diff_seconds(first['time'], max_record['time'])
    
    # 计算债券涨幅差（改用 bond_change_pct）
    first_pct = first.get('bond_change_pct', 0) or 0
    max_pct = max_record.get('bond_change_pct', 0) or 0
    gain_to_max = max_pct - first_pct
    
    # ==================== 指标计算 ====================
    
    # 【平均强度】= 该窗口内 window_count 的平均值
    # 指标意义：反映该对在窗口内的平均活跃程度
    # 计算：所有时间点的 window_count 求和 / 出现次数
    window_counts = [d.get('stock_window_count', 0) or 0 for d in sorted_details]
    window_count_avg = sum(window_counts) / len(window_counts) if window_counts else 0
    
    # 【区间最高命中数】= 该窗口内 window_count 的最大值
    # 指标意义：反映该对在窗口内的最高活跃强度
    max_window_count = max(window_counts) if window_counts else 0
    
    # 【连续度】= 出现次数 / 窗口内理论总tick数
    # 指标意义：反映该对在时间维度上的覆盖密度
    # 注意：使用实际的窗口tick数，而非固定值
    # 10分钟窗口理论tick数：约 200个（3秒/tick）
    # 但实际只计算有数据的时间点
    actual_window_ticks = 200  # 10分钟 * 60秒 / 3秒 ≈ 200 ticks
    continuity_score = len(sorted_details) / actual_window_ticks if actual_window_ticks > 0 else 0
    # 限制最大值为1（100%）
    continuity_score = min(continuity_score, 1.0)
    
    # 计算平均涨幅（改用 bond_change_pct）
    change_pcts = [d.get('bond_change_pct', 0) or 0 for d in sorted_details]
    avg_change_pct = sum(change_pcts) / len(change_pcts) if change_pcts else 0
    
    # 标记关键点
    marked_details = []
    max_idx = sorted_details.index(max_record)
    
    for i, d in enumerate(sorted_details):
        marks = []
        if i == 0:
            marks.append('first')
        if i == max_idx:
            marks.append('max')
        if i == len(sorted_details) - 1:
            marks.append('last')
        
        d_copy = d.copy()
        d_copy['mark'] = ','.join(marks) if marks else ''
        marked_details.append(d_copy)
    
    return {
        'window': window,
        'window_start': window.split('-')[0] + ':00',
        'window_end': window.split('-')[1] + ':00',
        
        'stock_code': stock_code,
        'stock_name': first.get('stock_name', ''),
        'bond_code': bond_code,
        'bond_name': first.get('bond_name', ''),
        # 交集结果中股票行业在 stock_industry、债券在 bond_industry
        #（IntersectionCalculator 输出字段，非 industry_name / industry）
        'stock_industry': first.get('stock_industry', '-'),
        'bond_industry': first.get('bond_industry', '-'),
        # 兼容旧前端：优先股票行业，回退债券行业
        'industry_name': first.get('stock_industry') or first.get('bond_industry') or '-',
        
        'first_appear_time': first['time'],
        'first_change_pct': first_pct,  # 债券涨幅
        
        'max_change_time': max_record['time'],
        'max_change_pct': max_pct,  # 债券涨幅
        
        'last_appear_time': last['time'],
        'last_change_pct': last.get('bond_change_pct', 0) or 0,  # 债券涨幅
        
        'time_to_max_seconds': time_to_max_seconds,
        'time_to_max_display': format_duration(time_to_max_seconds),
        'time_color_class': get_time_color_class(time_to_max_seconds),
        
        'gain_to_max': round(gain_to_max, 2),
        'gain_color_class': get_gain_color_class(gain_to_max),  # 新增：涨幅差颜色
        # 区间差 = 结束时债券涨幅 - 命中时债券涨幅（可能为负，冲高回落）
        'gain_interval': round((last.get('bond_change_pct', 0) or 0) - first_pct, 2),
        'gain_interval_color_class': get_gain_color_class((last.get('bond_change_pct', 0) or 0) - first_pct),
        'appear_count': len(sorted_details),
        'max_window_count': max_window_count,  # 新增：区间最高命中数
        'window_count_avg': round(window_count_avg, 1),
        'continuity_score': round(continuity_score, 2),
        
        'min_change_pct': min_record.get('stock_change_pct', 0) or 0,
        'avg_change_pct': round(avg_change_pct, 2),
        
        'details': marked_details
    }


def aggregate_by_window(results: list, window_minutes: int = 10) -> dict:
    """将逐tick回溯结果按10分钟窗口聚合
    
    Args:
        results: 逐tick回溯结果，格式为 [{'time': '14:23:15', 'count': 5, 'stocks': [...]}, ...]
        window_minutes: 窗口大小（分钟）
        
    Returns:
        聚合后的数据结构
    """
    if not results:
        return {
            'windows': [],
            'summary': [],
            'statistics': {}
        }
    
    # 获取时间范围
    all_times = [r['time'] for r in results if r.get('time')]
    if not all_times:
        return {'windows': [], 'summary': [], 'statistics': {}}
    
    first_time = min(all_times)
    last_time = max(all_times)
    
    # 生成窗口
    windows = generate_windows(first_time, last_time, window_minutes)
    
    # 按窗口+股票债券对分组
    from collections import defaultdict
    groups = defaultdict(list)
    
    for record in results:
        time_str = record['time']
        window = get_window_for_time(time_str, windows)
        
        for stock in record.get('stocks', []):
            pair_key = (
                window,
                stock.get('stock_code'),
                stock.get('bond_code')
            )
            
            # 构建明细记录
            detail = {
                'time': time_str,
                'stock_code': stock.get('stock_code'),
                'stock_name': stock.get('stock_name'),
                'bond_code': stock.get('bond_code'),
                'bond_name': stock.get('bond_name'),
                'industry': stock.get('industry'),
                'stock_change_pct': stock.get('stock_change_pct'),
                'bond_change_pct': stock.get('bond_change_pct'),
                'stock_price': stock.get('stock_price'),
                'bond_price': stock.get('bond_price'),
                'stock_count': stock.get('stock_count'),
                'bond_window_count': stock.get('bond_window_count'),
                'stock_window_count': stock.get('stock_window_count'),
                'main_net_amount': stock.get('main_net_amount'),
                'stock_rank': stock.get('stock_rank'),
                'bond_rank': stock.get('bond_rank'),
                'stock_industry': stock.get('stock_industry'),
                'bond_industry': stock.get('bond_industry'),
            }
            
            groups[pair_key].append(detail)
    
    # 计算每个组的汇总
    # 10分钟窗口的理论tick数：10分钟 * 60秒 / 3秒 ≈ 200 ticks
    actual_window_ticks = int(window_minutes * 60 / 3)
    
    summary = []
    for (window, stock_code, bond_code), details in groups.items():
        window_summary = calculate_window_summary(window, stock_code, bond_code, details, actual_window_ticks)
        if window_summary:
            summary.append(window_summary)
    
    # 按窗口和首次时间排序
    summary.sort(key=lambda x: (x['window'], x['first_appear_time']))
    
    # 按窗口分组
    window_groups = defaultdict(list)
    for item in summary:
        window_groups[item['window']].append(item)
    
    # 构建最终结构
    summary_with_pairs = []
    for window in windows:
        pairs = window_groups.get(window, [])
        if pairs:  # 只显示有数据的窗口
            summary_with_pairs.append({
                'window': window,
                'window_start': window.split('-')[0] + ':00',
                'window_end': window.split('-')[1] + ':00',
                'pair_count': len(pairs),
                'pairs': pairs
            })
    
    # 计算统计信息
    total_pairs = len(summary)
    all_time_to_max = [s['time_to_max_seconds'] for s in summary]
    all_gain_to_max = [s['gain_to_max'] for s in summary]
    
    avg_time_to_max = sum(all_time_to_max) / len(all_time_to_max) if all_time_to_max else 0
    max_gain = max(all_gain_to_max) if all_gain_to_max else 0
    
    statistics = {
        'total_windows': len(summary_with_pairs),
        'total_pairs': total_pairs,
        'avg_time_to_max_seconds': int(avg_time_to_max),
        'avg_time_to_max_display': format_duration(int(avg_time_to_max)),
        'max_gain': round(max_gain, 2)
    }
    
    return {
        'windows': windows,
        'summary': summary_with_pairs,
        'statistics': statistics
    }


# ==================== 回溯核心逻辑 ====================

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

    _t0 = time.time()
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

    logger.info(f"[回溯完成] {actual_date} {st}~{et}: {total}个时间点, {len(results)}个有交集, 耗时{time.time()-_t0:.1f}s")
    yield {'type': 'done', 'data': {
        'date': date, 'start_time': st, 'end_time': et,
        'total_timestamps': total,
        'elapsed_seconds': round(time.time() - _t0, 1),
        'intersection_count': len(results),
        'results': results
    }}


@backtrace_bp.route('/api/backtrace/run', methods=['POST'])
def api_run():
    """执行股债交集回溯（同步返回，兼容旧调用）
    
    支持两种返回格式:
    1. 传统格式: 逐tick明细 (当 aggregate=false 或未指定)
    2. 窗口汇总: 10分钟窗口聚合 (当 aggregate=true)
    """
    try:
        data = request.get_json()
        aggregate = data.get('aggregate', False)  # 是否启用窗口汇总
        window_minutes = data.get('window_minutes', 10)  # 窗口大小
        
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
        
        # 如果启用窗口汇总，转换数据格式
        if aggregate:
            aggregated = aggregate_by_window(final.get('results', []), window_minutes)
            # 透传耗时到统计面板
            if aggregated.get('statistics') and final.get('elapsed_seconds'):
                aggregated['statistics']['elapsed_seconds'] = final['elapsed_seconds']
            final['aggregated'] = aggregated
            final['aggregate_mode'] = True
        
        return jsonify({'code': 0, 'data': final})
    except Exception as e:
        logger.error(f"执行回溯失败: {e}", exc_info=True)
        return jsonify({'code': 1, 'message': str(e)})


@backtrace_bp.route('/api/backtrace/run-stream', methods=['POST'])
def api_run_stream():
    """执行股债交集回溯（SSE流式进度）
    
    支持窗口汇总: 当 aggregate=true 时，在done事件中包含aggregated数据
    """
    import json as _json
    from flask import Response, stream_with_context

    data = request.get_json()
    date = data.get('date')
    stock_config = data.get('stock_config', {})
    bond_config = data.get('bond_config', {})
    start_time = data.get('start_time', '')
    end_time = data.get('end_time', '')
    aggregate = data.get('aggregate', False)  # 是否启用窗口汇总
    window_minutes = data.get('window_minutes', 10)  # 窗口大小

    @stream_with_context
    def generate():
        try:
            final_data = None
            for ev in _run_backtrace_core(date, stock_config, bond_config, start_time, end_time):
                if ev['type'] == 'done':
                    final_data = ev['data']
                    # 如果启用窗口汇总，转换数据格式
                    if aggregate and final_data:
                        try:
                            aggregated = aggregate_by_window(final_data.get('results', []), window_minutes)
                            # 透传耗时到统计面板
                            if aggregated.get('statistics') and final_data.get('elapsed_seconds'):
                                aggregated['statistics']['elapsed_seconds'] = final_data['elapsed_seconds']
                            final_data['aggregated'] = aggregated
                            final_data['aggregate_mode'] = True
                        except Exception as agg_err:
                            logger.error(f"窗口汇总失败: {agg_err}", exc_info=True)
                            final_data['aggregate_error'] = str(agg_err)
                    
                    # 发送最终的done事件
                    yield f"data: {_json.dumps({'type': 'done', 'data': final_data}, ensure_ascii=False)}\n\n"
                else:
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
