#!/usr/bin/env python3
"""
大盘趋势时间区间识别脚本（向上/向下）

使用方式：
    python scripts/detect_market_trend.py 20260721
    python scripts/detect_market_trend.py 20260721 --direction up
    python scripts/detect_market_trend.py 20260721 --direction down
    python scripts/detect_market_trend.py 20260721 --direction both --min_duration 5

或者直接修改下方 CONFIG 参数运行：
    python scripts/detect_market_trend.py

说明（四状态判定：斜率主导 + 分位数动态阈值）：
    - S_thr = |斜率|的分位数（默认40%分位），C_thr = |涨跌幅|的分位数
    - 向上：slope > +S_thr 且 change > 0   （趋势向上 + 在涨）
    - 向下：slope < -S_thr 且 change < 0   （趋势向下 + 在跌）
    - 震荡：|slope| ≤ S_thr 且 |change| ≤ C_thr  （无趋势 + 波动小）
    - 过渡：其他（背离 / 趋势转折点）
    - 阈值随当天数据分布自适应，适配涨/跌/横盘各种行情
    - both/all 模式一次加载数据，各方向共用，不会翻倍耗时
"""

# ==================== 参数配置区（直接修改这里）====================
CONFIG = {
    # 分析日期，格式 YYYYMMDD
    'date': '20260713',
    
    # 分析方向：'up'(仅向上) | 'down'(仅向下) | 'sideways'(仅震荡)
    #          | 'both'(上+下) | 'all'(上+下+震荡+过渡占比)
    'direction': 'all',
    
    # 最小持续分钟数（过滤噪音）
    'min_duration': 0.5,  # 0.5分钟（30秒）
    
    # ===== 阈值策略 =====
    # 'quantile'(推荐,分位数动态阈值,自适应行情) | 'fixed'(固定阈值兜底)
    'threshold_mode': 'quantile',
    
    # 分位数模式参数（threshold_mode='quantile'时生效）
    'slope_quantile': 0.40,        # |斜率|的分位数作为 S_thr
    'change_quantile': 0.40,       # |涨跌幅|的分位数作为 C_thr
    
    # 固定阈值兜底参数（threshold_mode='fixed'时生效）
    'slope_threshold': 0.001,      # |mkt_weighted_slope_2m| 门槛
    'change_threshold': 0.01,      # |mkt_change_1m_pct| 门槛
    
    # 区间合并参数
    'merge_gap_min': 2,            # 间隔小于2分钟的区间合并
}
# ================================================================

import sys
import argparse
from datetime import datetime

import pandas as pd
from sqlalchemy import text

from gs2026.utils import config_util, mysql_util


def get_engine():
    """获取数据库引擎"""
    return config_util.get_engine()


def load_mkt_data(date_str: str) -> pd.DataFrame:
    """
    加载大盘指标数据（一次查询，供上下方向复用）
    
    大盘指标存储在 ext_indicators JSON 列中，同一时刻所有债券的大盘值相同。
    【性能优化】不做全表 GROUP BY（145万行×TEXT列 JSON_EXTRACT 需50s+），
                改为只取一只全天成交的债券，行数降到~4800，再在pandas中解析JSON。
    
    Returns:
        DataFrame(time, mkt_weighted_slope_2m, mkt_change_1m_pct, mkt_price_acceleration)
        空表返回空 DataFrame
    """
    engine = get_engine()
    table = f"monitor_zq_sssj_{date_str}"
    
    with engine.connect() as conn:
        # 取任一债券作为大盘指标代表（LIMIT 1 瞬时返回）
        code_df = pd.read_sql(text(f"""
            SELECT bond_code
            FROM {table}
            WHERE time >= '14:50:00'
            LIMIT 1
        """), conn)
        if code_df.empty:
            return pd.DataFrame()
        rep_code = code_df['bond_code'].iloc[0]

        df_raw = pd.read_sql(text(f"""
            SELECT time, ext_indicators
            FROM {table}
            WHERE bond_code = :code
              AND time >= '09:30:00'
              AND ext_indicators IS NOT NULL
            ORDER BY time
        """), conn, params={'code': rep_code})

    if df_raw.empty:
        return pd.DataFrame()

    import json
    def _parse_ext(js):
        try:
            d = json.loads(js) if isinstance(js, str) else (js or {})
            return (
                d.get('mkt_weighted_slope_2m'),
                d.get('mkt_change_1m_pct'),
                d.get('mkt_price_acceleration'),
            )
        except Exception:
            return (None, None, None)

    parsed = df_raw['ext_indicators'].apply(_parse_ext)
    df = pd.DataFrame({
        'time': df_raw['time'].values,
        'mkt_weighted_slope_2m': pd.to_numeric([p[0] for p in parsed], errors='coerce'),
        'mkt_change_1m_pct': pd.to_numeric([p[1] for p in parsed], errors='coerce'),
        'mkt_price_acceleration': pd.to_numeric([p[2] for p in parsed], errors='coerce'),
    })
    return df


def compute_thresholds(df: pd.DataFrame):
    """
    计算判定阈值 (S_thr, C_thr)
    
    - threshold_mode='quantile'：基于当天 |斜率|/|涨跌幅| 的分位数（自适应行情，推荐）
    - threshold_mode='fixed'   ：使用 CONFIG 固定值兜底
    
    Returns:
        (S_thr, C_thr)
    """
    mode = CONFIG.get('threshold_mode', 'quantile')
    if mode == 'fixed' or df.empty:
        return CONFIG['slope_threshold'], CONFIG['change_threshold']

    s_abs = df['mkt_weighted_slope_2m'].abs()
    c_abs = df['mkt_change_1m_pct'].abs()
    s_thr = float(s_abs.quantile(CONFIG['slope_quantile']))
    c_thr = float(c_abs.quantile(CONFIG['change_quantile']))
    # 防止极端情况阈值为0（全零数据）
    if s_thr <= 0:
        s_thr = CONFIG['slope_threshold']
    if c_thr <= 0:
        c_thr = CONFIG['change_threshold']
    return s_thr, c_thr


def _detect_periods(df: pd.DataFrame, direction: str,
                    slope_thr: float, change_thr: float,
                    min_duration: float, merge_gap: float) -> list:
    """
    通用趋势区间检测（斜率主导 + 涨跌幅方向确认）
    
    判定逻辑：
        向上 = slope > +S_thr AND change > 0        （趋势向上 + 在涨）
        向下 = slope < -S_thr AND change < 0        （趋势向下 + 在跌）
        震荡 = |slope| ≤ S_thr AND |change| ≤ C_thr  （无趋势 + 波动小）
    
    Args:
        df: load_mkt_data() 返回的数据
        direction: 'up' | 'down' | 'sideways'
        slope_thr: S_thr（斜率阈值，正值）
        change_thr: C_thr（涨跌幅阈值，正值，仅震荡用）
        min_duration: 最小持续分钟数
        merge_gap: 合并间隔（分钟）
    
    Returns:
        区间列表。字段前缀随方向变化（up_/down_/sideways_）。
    """
    if df.empty:
        return []

    work = df.copy()
    prefix = direction

    if direction == 'up':
        # 斜率向上达标 + 涨跌幅方向为正（不要求幅度）
        work['is_active'] = (
            (work['mkt_weighted_slope_2m'] > slope_thr) &
            (work['mkt_change_1m_pct'] > 0)
        ).astype(int)
    elif direction == 'down':
        # 斜率向下达标 + 涨跌幅方向为负
        work['is_active'] = (
            (work['mkt_weighted_slope_2m'] < -slope_thr) &
            (work['mkt_change_1m_pct'] < 0)
        ).astype(int)
    else:  # sideways（震荡：斜率和涨幅绝对值都在阈值内 = 无明显方向）
        work['is_active'] = (
            (work['mkt_weighted_slope_2m'].abs() <= slope_thr) &
            (work['mkt_change_1m_pct'].abs() <= change_thr)
        ).astype(int)

    # 识别连续区间
    work['group'] = (work['is_active'].diff() != 0).cumsum()
    groups = work[work['is_active'] == 1].groupby('group')

    periods = []
    for _, g in groups:
        start_time = pd.to_datetime(g['time'].iloc[0])
        end_time = pd.to_datetime(g['time'].iloc[-1])
        duration_min = round((end_time - start_time).total_seconds() / 60, 1)

        if duration_min >= min_duration:
            period = {
                f'{prefix}_start_time': g['time'].iloc[0],
                f'{prefix}_end_time': g['time'].iloc[-1],
                f'{prefix}_duration_min': duration_min,
                'avg_slope': round(g['mkt_weighted_slope_2m'].mean(), 4),
            }
            if direction == 'up':
                period['max_change_pct'] = round(g['mkt_change_1m_pct'].max(), 4)
            elif direction == 'down':
                period['min_change_pct'] = round(g['mkt_change_1m_pct'].min(), 4)
            else:  # sideways
                period['avg_change_pct'] = round(g['mkt_change_1m_pct'].mean(), 4)
            periods.append(period)

    # 合并相近区间
    periods = _merge_close_periods(periods, merge_gap, direction)

    # 合并后再用 min_duration 过滤
    periods = [p for p in periods if p[f'{prefix}_duration_min'] >= min_duration]

    return periods


def _merge_close_periods(periods, gap_min, direction='up'):
    """
    合并间隔小于gap_min分钟的相近区间
    
    Args:
        periods: 区间列表
        gap_min: 合并阈值（分钟）
        direction: 'up' | 'down'（决定字段前缀和涨跌幅聚合方向）
    
    Returns:
        合并后的区间列表
    """
    if len(periods) <= 1:
        return periods

    prefix = direction
    if direction == 'up':
        change_key = 'max_change_pct'
    elif direction == 'down':
        change_key = 'min_change_pct'
    else:
        change_key = 'avg_change_pct'

    merged = []
    current = periods[0].copy()

    for next_p in periods[1:]:
        current_end = pd.to_datetime(current[f'{prefix}_end_time'])
        next_start = pd.to_datetime(next_p[f'{prefix}_start_time'])
        gap = (next_start - current_end).total_seconds() / 60

        if gap <= gap_min:
            # 合并区间
            current[f'{prefix}_end_time'] = next_p[f'{prefix}_end_time']
            current[f'{prefix}_duration_min'] = round(
                (pd.to_datetime(current[f'{prefix}_end_time']) -
                 pd.to_datetime(current[f'{prefix}_start_time'])).total_seconds() / 60, 1
            )
            # 加权平均斜率
            total_min = current[f'{prefix}_duration_min'] + next_p[f'{prefix}_duration_min']
            if total_min > 0:
                current['avg_slope'] = round(
                    (current['avg_slope'] * current[f'{prefix}_duration_min'] +
                     next_p['avg_slope'] * next_p[f'{prefix}_duration_min']) / total_min, 4
                )
            # 涨跌幅聚合：向上取最大，向下取最小，震荡取加权平均
            if direction == 'up':
                current[change_key] = round(max(current[change_key], next_p[change_key]), 4)
            elif direction == 'down':
                current[change_key] = round(min(current[change_key], next_p[change_key]), 4)
            else:  # sideways 加权平均
                if total_min > 0:
                    current[change_key] = round(
                        (current[change_key] * current[f'{prefix}_duration_min'] +
                         next_p[change_key] * next_p[f'{prefix}_duration_min']) / total_min, 4
                    )
        else:
            merged.append(current)
            current = next_p.copy()

    merged.append(current)
    return merged


# ========== 对外API（向后兼容 + 新增）==========

def _resolve_thr(df, slope_thr, change_thr):
    """阈值解析：None时按CONFIG策略动态计算，否则用传入值"""
    if slope_thr is None or change_thr is None:
        return compute_thresholds(df)
    return slope_thr, change_thr


def detect_market_up(date_str: str, min_duration: float = 0.5,
                     slope_thr: float = None, change_thr: float = None):
    """识别大盘向上时间区间（向后兼容接口；阈值None时自适应）"""
    df = load_mkt_data(date_str)
    if df.empty:
        return []
    s, c = _resolve_thr(df, slope_thr, change_thr)
    return _detect_periods(df, 'up', s, c,
                           min_duration, CONFIG['merge_gap_min'])


def detect_market_down(date_str: str, min_duration: float = 0.5,
                       slope_thr: float = None, change_thr: float = None):
    """识别大盘向下时间区间（阈值None时自适应）"""
    df = load_mkt_data(date_str)
    if df.empty:
        return []
    s, c = _resolve_thr(df, slope_thr, change_thr)
    return _detect_periods(df, 'down', s, c,
                           min_duration, CONFIG['merge_gap_min'])


def detect_market_sideways(date_str: str, min_duration: float = 0.5,
                           slope_thr: float = None, change_thr: float = None):
    """识别大盘震荡时间区间（阈值None时自适应）"""
    df = load_mkt_data(date_str)
    if df.empty:
        return []
    s, c = _resolve_thr(df, slope_thr, change_thr)
    return _detect_periods(df, 'sideways', s, c,
                           min_duration, CONFIG['merge_gap_min'])


def detect_market_trends(date_str: str, min_duration: float = 0.5,
                         slope_thr: float = None, change_thr: float = None):
    """
    一次加载数据，同时识别向上、向下、震荡区间（推荐用于both模式）
    
    Returns:
        dict: {'up': [...], 'down': [...], 'sideways': [...]}
    """
    df = load_mkt_data(date_str)
    if df.empty:
        return {'up': [], 'down': [], 'sideways': []}
    s, c = _resolve_thr(df, slope_thr, change_thr)
    return {
        'up': _detect_periods(df, 'up', s, c,
                              min_duration, CONFIG['merge_gap_min']),
        'down': _detect_periods(df, 'down', s, c,
                                min_duration, CONFIG['merge_gap_min']),
        'sideways': _detect_periods(df, 'sideways', s, c,
                                    min_duration, CONFIG['merge_gap_min']),
    }


def _print_periods(periods, direction):
    """打印区间列表"""
    prefix = direction
    label = {'up': '向上', 'down': '向下', 'sideways': '震荡'}[direction]
    if direction == 'up':
        change_key, change_label = 'max_change_pct', '最大涨幅'
    elif direction == 'down':
        change_key, change_label = 'min_change_pct', '最大跌幅'
    else:
        change_key, change_label = 'avg_change_pct', '平均涨跌'

    if not periods:
        print(f"【{label}区间】未找到\n")
        return

    total_min = sum(p[f'{prefix}_duration_min'] for p in periods)
    print(f"【{label}区间】找到 {len(periods)} 个，累计 {round(total_min, 1)} 分钟:\n")
    for i, p in enumerate(periods, 1):
        print(f"  区间 {i}: {p[f'{prefix}_start_time']} - {p[f'{prefix}_end_time']} "
              f"({p[f'{prefix}_duration_min']}分钟) "
              f"斜率{p['avg_slope']:+} {change_label}{p[change_key]:+}%")
    print()


def main():
    parser = argparse.ArgumentParser(description='大盘趋势时间区间识别（向上/向下/震荡）')
    parser.add_argument('date', nargs='?', help='日期 YYYYMMDD（可选，默认使用CONFIG）')
    parser.add_argument('--direction', choices=['up', 'down', 'sideways', 'both', 'all'],
                        help='分析方向 up|down|sideways|both|all（可选，默认使用CONFIG）')
    parser.add_argument('--min_duration', type=float, help='最小持续分钟数（可选，默认使用CONFIG）')
    args = parser.parse_args()

    date_str = args.date if args.date else CONFIG['date']
    direction = args.direction if args.direction else CONFIG['direction']
    min_duration = args.min_duration if args.min_duration is not None else CONFIG['min_duration']

    print(f"分析日期: {date_str}")
    print(f"方向: {direction}")

    # 一次加载数据
    df = load_mkt_data(date_str)
    if df.empty:
        print(f"日期 {date_str} 无数据")
        return

    # 计算阈值（分位数动态 或 固定兜底）
    slope_thr, change_thr = compute_thresholds(df)
    mode = CONFIG.get('threshold_mode', 'quantile')
    if mode == 'quantile':
        print(f"阈值策略: 分位数(S={CONFIG['slope_quantile']:.0%}, C={CONFIG['change_quantile']:.0%}) "
              f"→ S_thr={slope_thr:.5f}, C_thr={change_thr:.4f}")
    else:
        print(f"阈值策略: 固定 → S_thr={slope_thr:.5f}, C_thr={change_thr:.4f}")
    print(f"最小持续: {min_duration}分钟")
    print("=" * 60)

    # both = 向上+向下；all = 向上+向下+震荡
    show_up = direction in ('up', 'both', 'all')
    show_down = direction in ('down', 'both', 'all')
    show_sideways = direction in ('sideways', 'all')

    results = {}
    if show_up:
        results['up'] = _detect_periods(df, 'up', slope_thr, change_thr,
                                        min_duration, CONFIG['merge_gap_min'])
        _print_periods(results['up'], 'up')
    if show_down:
        results['down'] = _detect_periods(df, 'down', slope_thr, change_thr,
                                          min_duration, CONFIG['merge_gap_min'])
        _print_periods(results['down'], 'down')
    if show_sideways:
        results['sideways'] = _detect_periods(df, 'sideways', slope_thr, change_thr,
                                              min_duration, CONFIG['merge_gap_min'])
        _print_periods(results['sideways'], 'sideways')

    # 时间占比统计（基于全天交易时长）
    _print_summary(df, results, direction)


def _print_summary(df, results, direction):
    """打印各状态时间占比统计"""
    # 全天交易时长（首末tick之差，扣除午休90分钟）
    t_start = pd.to_datetime(df['time'].iloc[0])
    t_end = pd.to_datetime(df['time'].iloc[-1])
    total_span_min = (t_end - t_start).total_seconds() / 60
    # 若跨越午休则扣除90分钟
    lunch_start = pd.to_datetime(df['time'].iloc[0]).replace(hour=11, minute=30, second=0)
    lunch_end = pd.to_datetime(df['time'].iloc[0]).replace(hour=13, minute=0, second=0)
    if t_start < lunch_start and t_end > lunch_end:
        total_span_min -= 90
    total_span_min = max(total_span_min, 1)

    print("=" * 60)
    print(f"时间占比统计（全天有效交易约 {round(total_span_min, 1)} 分钟）:")

    labels = {'up': '向上', 'down': '向下', 'sideways': '震荡'}
    accounted = 0.0
    for key in ('up', 'down', 'sideways'):
        if key in results:
            prefix = key
            mins = sum(p[f'{prefix}_duration_min'] for p in results[key])
            accounted += mins
            pct = mins / total_span_min * 100
            print(f"  {labels[key]}: {round(mins, 1)} 分钟 ({round(pct, 1)}%)")

    # 过渡/背离态（仅在 all 模式下有意义，三态都统计了才能算）
    if direction == 'all':
        transition = max(total_span_min - accounted, 0)
        pct = transition / total_span_min * 100
        print(f"  过渡/背离: {round(transition, 1)} 分钟 ({round(pct, 1)}%)")
        print("  （过渡/背离 = 趋势转折点/单指标达标/被过滤的短趋势，非震荡）")
    print()


if __name__ == '__main__':
    main()
