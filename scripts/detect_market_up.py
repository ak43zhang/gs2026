#!/usr/bin/env python3
"""
大盘向上时间区间识别脚本

使用方式：
    python scripts/detect_market_up.py 20260721
    python scripts/detect_market_up.py 20260721 --min_duration 5

或者直接修改下方 CONFIG 参数运行：
    python scripts/detect_market_up.py
"""

# ==================== 参数配置区（直接修改这里）====================
CONFIG = {
    # 分析日期，格式 YYYYMMDD
    'date': '20260714',
    
    # 最小持续分钟数（过滤噪音）
    'min_duration': 0.5,  # 改为0.5分钟（30秒）
    
    # 向上判定阈值【根据实际数据调整，原0.1过高】
    'slope_threshold': 0.001,      # mkt_weighted_slope_2m > 0.001
    'change_threshold': 0.01,      # mkt_change_1m_pct > 0.02 (大盘涨幅慢，从0.05降至0.02)
    # 【方案B】移除加速度条件，只用斜率和涨幅
    # 'acceleration_threshold': 0,   # 已移除
    
    # 【新增】区间合并参数
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
    url = config_util.get_config("common.url")
    return config_util.get_engine()


def detect_market_up(date_str: str, min_duration: int = 3,
                     slope_thr: float = 0.1, change_thr: float = 0.05):
    """
    识别大盘向上时间区间（方案B：只用斜率和涨幅）
    
    Args:
        date_str: 日期格式 YYYYMMDD
        min_duration: 最小持续分钟数
        slope_thr: 斜率阈值
        change_thr: 涨幅阈值
        accel_thr: 加速度阈值
    
    Returns:
        list: 向上区间列表
    """
    engine = get_engine()
    table = f"monitor_zq_sssj_{date_str}"
    
    # 读取数据（取第一条记录的大盘指标即可，因为大盘指标每行相同）
    sql = text(f"""
        SELECT DISTINCT time, 
               mkt_weighted_slope_2m,
               mkt_change_1m_pct,
               mkt_price_acceleration
        FROM {table}
        WHERE time >= '09:30:00'
        ORDER BY time
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    
    if df.empty:
        print(f"日期 {date_str} 无数据")
        return []
    
    # 【修复】转换数据类型为数值
    df['mkt_weighted_slope_2m'] = pd.to_numeric(df['mkt_weighted_slope_2m'], errors='coerce')
    df['mkt_change_1m_pct'] = pd.to_numeric(df['mkt_change_1m_pct'], errors='coerce')
    df['mkt_price_acceleration'] = pd.to_numeric(df['mkt_price_acceleration'], errors='coerce')
    
    # 判定向上状态（只用斜率和涨幅，移除加速度）
    df['is_up'] = (
        (df['mkt_weighted_slope_2m'] > slope_thr) &
        (df['mkt_change_1m_pct'] > change_thr)
    ).astype(int)
    
    # 识别连续区间
    df['group'] = (df['is_up'].diff() != 0).cumsum()
    groups = df[df['is_up'] == 1].groupby('group')
    
    # 汇总结果
    up_periods = []
    for _, g in groups:
        # 【修复】先计算实际分钟数，再用它过滤
        start_time = pd.to_datetime(g['time'].iloc[0])
        end_time = pd.to_datetime(g['time'].iloc[-1])
        duration_min = round((end_time - start_time).total_seconds() / 60, 1)
        
        # 【修复】用实际分钟数过滤，而不是记录条数
        if duration_min >= min_duration:
            up_periods.append({
                'up_start_time': g['time'].iloc[0],
                'up_end_time': g['time'].iloc[-1],
                'up_duration_min': duration_min,  # 实际分钟数
                'avg_slope': round(g['mkt_weighted_slope_2m'].mean(), 4),
                'max_change_pct': round(g['mkt_change_1m_pct'].max(), 4)
            })
    
    # 【新增】合并相近区间
    up_periods = _merge_close_periods(up_periods, CONFIG['merge_gap_min'])
    
    # 【方案B】合并后，再用min_duration过滤总时长
    up_periods = [p for p in up_periods if p['up_duration_min'] >= min_duration]
    
    return up_periods


def _merge_close_periods(periods, gap_min):
    """
    合并间隔小于gap_min分钟的相近区间
    
    Args:
        periods: 区间列表
        gap_min: 合并阈值（分钟）
    
    Returns:
        合并后的区间列表
    """
    if len(periods) <= 1:
        return periods
    
    merged = []
    current = periods[0].copy()
    
    for next_p in periods[1:]:
        # 计算当前区间结束到下一个区间开始的间隔（分钟）
        current_end = pd.to_datetime(current['up_end_time'])
        next_start = pd.to_datetime(next_p['up_start_time'])
        gap = (next_start - current_end).total_seconds() / 60
        
        if gap <= gap_min:
            # 合并区间
            current['up_end_time'] = next_p['up_end_time']
            current['up_duration_min'] = round(
                (pd.to_datetime(current['up_end_time']) - pd.to_datetime(current['up_start_time'])).total_seconds() / 60, 1
            )
            # 加权平均斜率
            total_min = current['up_duration_min'] + next_p['up_duration_min']
            if total_min > 0:
                current['avg_slope'] = round(
                    (current['avg_slope'] * current['up_duration_min'] + next_p['avg_slope'] * next_p['up_duration_min']) / total_min, 4
                )
            # 最大涨幅取两者最大
            current['max_change_pct'] = round(max(current['max_change_pct'], next_p['max_change_pct']), 4)
        else:
            # 不合并，保存当前区间，开始新区间
            merged.append(current)
            current = next_p.copy()
    
    # 添加最后一个区间
    merged.append(current)
    
    return merged


def main():
    parser = argparse.ArgumentParser(description='大盘向上时间区间识别')
    parser.add_argument('date', nargs='?', help='日期 YYYYMMDD（可选，默认使用CONFIG）')
    parser.add_argument('--min_duration', type=int, help='最小持续分钟数（可选，默认使用CONFIG）')
    args = parser.parse_args()
    
    # 优先使用命令行参数，否则使用CONFIG
    date_str = args.date if args.date else CONFIG['date']
    min_duration = args.min_duration if args.min_duration else CONFIG['min_duration']
    
    print(f"分析日期: {date_str}")
    print(f"阈值: slope>{CONFIG['slope_threshold']}, change>{CONFIG['change_threshold']} (已移除加速度条件)")
    print("-" * 60)
    
    periods = detect_market_up(
        date_str, 
        min_duration,
        CONFIG['slope_threshold'],
        CONFIG['change_threshold']
    )
    
    if not periods:
        print("未找到向上区间")
        return
    
    print(f"找到 {len(periods)} 个向上区间:\n")
    
    for i, p in enumerate(periods, 1):
        print(f"区间 {i}:")
        print(f"  up_start_time:  {p['up_start_time']}")
        print(f"  up_end_time:    {p['up_end_time']}")
        print(f"  up_duration_min: {p['up_duration_min']}")
        print(f"  avg_slope:      {p['avg_slope']}")
        print(f"  max_change_pct: {p['max_change_pct']}")
        print()


if __name__ == '__main__':
    main()
