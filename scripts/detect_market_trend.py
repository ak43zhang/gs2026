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

说明：
    - 向上区间：mkt_weighted_slope_2m > +slope_thr 且 mkt_change_1m_pct > +change_thr
    - 向下区间：mkt_weighted_slope_2m < -slope_thr 且 mkt_change_1m_pct < -change_thr
    - both 模式一次加载数据，两个方向共用，不会翻倍耗时
"""

# ==================== 参数配置区（直接修改这里）====================
CONFIG = {
    # 分析日期，格式 YYYYMMDD
    'date': '20260713',
    
    # 分析方向：'up'(仅向上) | 'down'(仅向下) | 'both'(上下都看)
    'direction': 'both',
    
    # 最小持续分钟数（过滤噪音）
    'min_duration': 0.5,  # 0.5分钟（30秒）
    
    # 趋势判定阈值（对称使用：向上用 +thr，向下用 -thr）
    'slope_threshold': 0.001,      # |mkt_weighted_slope_2m| > 0.001
    'change_threshold': 0.01,      # |mkt_change_1m_pct| > 0.01
    
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


def _detect_periods(df: pd.DataFrame, direction: str,
                    slope_thr: float, change_thr: float,
                    min_duration: float, merge_gap: float) -> list:
    """
    通用趋势区间检测
    
    Args:
        df: load_mkt_data() 返回的数据
        direction: 'up' | 'down'
        slope_thr: 斜率阈值（正值，内部按方向取正负）
        change_thr: 涨跌幅阈值（正值，内部按方向取正负）
        min_duration: 最小持续分钟数
        merge_gap: 合并间隔（分钟）
    
    Returns:
        区间列表。字段前缀随方向变化（up_/down_），
        向上含 max_change_pct（最大涨幅），向下含 min_change_pct（最大跌幅）。
    """
    if df.empty:
        return []

    work = df.copy()
    prefix = direction  # 'up' or 'down'

    if direction == 'up':
        work['is_active'] = (
            (work['mkt_weighted_slope_2m'] > slope_thr) &
            (work['mkt_change_1m_pct'] > change_thr)
        ).astype(int)
    else:  # down
        work['is_active'] = (
            (work['mkt_weighted_slope_2m'] < -slope_thr) &
            (work['mkt_change_1m_pct'] < -change_thr)
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
            else:
                period['min_change_pct'] = round(g['mkt_change_1m_pct'].min(), 4)
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
    change_key = 'max_change_pct' if direction == 'up' else 'min_change_pct'

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
            # 涨跌幅聚合：向上取最大，向下取最小
            if direction == 'up':
                current[change_key] = round(max(current[change_key], next_p[change_key]), 4)
            else:
                current[change_key] = round(min(current[change_key], next_p[change_key]), 4)
        else:
            merged.append(current)
            current = next_p.copy()

    merged.append(current)
    return merged


# ========== 对外API（向后兼容 + 新增）==========

def detect_market_up(date_str: str, min_duration: float = 0.5,
                     slope_thr: float = 0.001, change_thr: float = 0.01):
    """识别大盘向上时间区间（向后兼容接口）"""
    df = load_mkt_data(date_str)
    if df.empty:
        return []
    return _detect_periods(df, 'up', slope_thr, change_thr,
                           min_duration, CONFIG['merge_gap_min'])


def detect_market_down(date_str: str, min_duration: float = 0.5,
                       slope_thr: float = 0.001, change_thr: float = 0.01):
    """识别大盘向下时间区间"""
    df = load_mkt_data(date_str)
    if df.empty:
        return []
    return _detect_periods(df, 'down', slope_thr, change_thr,
                           min_duration, CONFIG['merge_gap_min'])


def detect_market_trends(date_str: str, min_duration: float = 0.5,
                         slope_thr: float = 0.001, change_thr: float = 0.01):
    """
    一次加载数据，同时识别向上和向下区间（推荐用于both模式）
    
    Returns:
        dict: {'up': [...], 'down': [...]}
    """
    df = load_mkt_data(date_str)
    if df.empty:
        return {'up': [], 'down': []}
    return {
        'up': _detect_periods(df, 'up', slope_thr, change_thr,
                              min_duration, CONFIG['merge_gap_min']),
        'down': _detect_periods(df, 'down', slope_thr, change_thr,
                                min_duration, CONFIG['merge_gap_min']),
    }


def _print_periods(periods, direction):
    """打印区间列表"""
    prefix = direction
    label = '向上' if direction == 'up' else '向下'
    change_key = 'max_change_pct' if direction == 'up' else 'min_change_pct'
    change_label = '最大涨幅' if direction == 'up' else '最大跌幅'

    if not periods:
        print(f"【{label}区间】未找到\n")
        return

    print(f"【{label}区间】找到 {len(periods)} 个:\n")
    for i, p in enumerate(periods, 1):
        print(f"  区间 {i}: {p[f'{prefix}_start_time']} - {p[f'{prefix}_end_time']} "
              f"({p[f'{prefix}_duration_min']}分钟) "
              f"斜率{p['avg_slope']:+} {change_label}{p[change_key]:+}%")
    print()


def main():
    parser = argparse.ArgumentParser(description='大盘趋势时间区间识别（向上/向下）')
    parser.add_argument('date', nargs='?', help='日期 YYYYMMDD（可选，默认使用CONFIG）')
    parser.add_argument('--direction', choices=['up', 'down', 'both'],
                        help='分析方向 up|down|both（可选，默认使用CONFIG）')
    parser.add_argument('--min_duration', type=float, help='最小持续分钟数（可选，默认使用CONFIG）')
    args = parser.parse_args()

    date_str = args.date if args.date else CONFIG['date']
    direction = args.direction if args.direction else CONFIG['direction']
    min_duration = args.min_duration if args.min_duration is not None else CONFIG['min_duration']

    slope_thr = CONFIG['slope_threshold']
    change_thr = CONFIG['change_threshold']

    print(f"分析日期: {date_str}")
    print(f"方向: {direction}")
    print(f"阈值: |slope|>{slope_thr}, |change|>{change_thr}, 最小持续{min_duration}分钟")
    print("=" * 60)

    # 一次加载数据，按方向输出
    df = load_mkt_data(date_str)
    if df.empty:
        print(f"日期 {date_str} 无数据")
        return

    if direction in ('up', 'both'):
        up_periods = _detect_periods(df, 'up', slope_thr, change_thr,
                                     min_duration, CONFIG['merge_gap_min'])
        _print_periods(up_periods, 'up')

    if direction in ('down', 'both'):
        down_periods = _detect_periods(df, 'down', slope_thr, change_thr,
                                       min_duration, CONFIG['merge_gap_min'])
        _print_periods(down_periods, 'down')


if __name__ == '__main__':
    main()
