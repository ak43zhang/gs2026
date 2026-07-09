#!/usr/bin/env python3
"""
回填优化版斜率指标到历史数据

用法:
    python backfill_optimized_indicators.py --date 20260709
    python backfill_optimized_indicators.py --date 20260709 --table monitor_zq_sssj_20260709
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy import text
from gs2026.dashboard.services.data_service import DataService
from gs2026.dashboard2.services.bond_indicators import calc_weighted_slope, calc_change_rate


def backfill_indicators(date_str: str, table_name: str = None):
    """
    回填指定日期的优化指标
    
    Args:
        date_str: 日期 YYYYMMDD
        table_name: 表名，默认 monitor_zq_sssj_{date_str}
    """
    if table_name is None:
        table_name = f"monitor_zq_sssj_{date_str}"
    
    print(f"[开始] 回填 {table_name} 的优化指标")
    
    ds = DataService()
    
    # 检查表是否存在
    with ds.engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table_name}'
        """))
        if result.scalar() == 0:
            print(f"[错误] 表 {table_name} 不存在")
            return
    
    # 读取数据
    print(f"[加载] 读取 {table_name} 数据...")
    with ds.engine.connect() as conn:
        df = pd.read_sql(
            text(f"SELECT * FROM {table_name} ORDER BY bond_code, time"),
            conn
        )
    
    if df.empty:
        print(f"[警告] 表 {table_name} 无数据")
        return
    
    print(f"[加载] 共 {len(df)} 行数据")
    
    # 添加新指标列
    df['weighted_slope_2m'] = 0.0
    df['change_1m_pct'] = 0.0
    df['price_acceleration'] = 0.0
    
    # 按债券分组计算
    print(f"[计算] 计算加权斜率和变化率...")
    
    for bond_code, group in df.groupby('bond_code'):
        group = group.sort_values('time')
        prices = group['price'].values
        
        # 将时间转换为秒（从当天开始）
        times = pd.to_datetime(group['time'], format='%H%M%S')
        seconds = (times - times.iloc[0]).dt.total_seconds().values
        
        # 计算每个时间点的指标
        for i, idx in enumerate(group.index):
            if i < 2:
                continue
                
            # 获取2分钟窗口内的数据（约120秒）
            window_start = seconds[i] - 120
            window_mask = seconds[:i+1] >= window_start
            
            if window_mask.sum() < 2:
                continue
                
            window_prices = prices[:i+1][window_mask]
            window_times = seconds[:i+1][window_mask]
            
            # 计算加权斜率
            slope = calc_weighted_slope(window_prices, window_times, half_life=30)
            df.at[idx, 'weighted_slope_2m'] = slope
            
            # 计算1分钟变化率
            if i >= 1 and seconds[i] - seconds[i-1] <= 120:  # 确保是连续数据
                change = calc_change_rate(prices[i], prices[i-1])
                df.at[idx, 'change_1m_pct'] = change
    
    # 计算加速度（斜率的变化）
    print(f"[计算] 计算加速度...")
    for bond_code, group in df.groupby('bond_code'):
        group = group.sort_values('time')
        slopes = group['weighted_slope_2m'].values
        
        for i, idx in enumerate(group.index):
            if i >= 1:
                df.at[idx, 'price_acceleration'] = slopes[i] - slopes[i-1]
    
    # 计算大盘指标（所有债券的平均）
    print(f"[计算] 计算大盘指标...")
    for time_val, group in df.groupby('time'):
        df.loc[group.index, 'mkt_weighted_slope_2m'] = group['weighted_slope_2m'].mean()
        df.loc[group.index, 'mkt_change_1m_pct'] = group['change_1m_pct'].mean()
        df.loc[group.index, 'mkt_acceleration'] = group['price_acceleration'].mean()
    
    # 更新数据库
    print(f"[保存] 更新数据库...")
    with ds.engine.connect() as conn:
        for idx, row in df.iterrows():
            conn.execute(text(f"""
                UPDATE {table_name} 
                SET weighted_slope_2m = :slope,
                    change_1m_pct = :change,
                    price_acceleration = :accel,
                    mkt_weighted_slope_2m = :mkt_slope,
                    mkt_change_1m_pct = :mkt_change,
                    mkt_acceleration = :mkt_accel
                WHERE bond_code = :code AND time = :time
            """), {
                'slope': float(row['weighted_slope_2m']),
                'change': float(row['change_1m_pct']),
                'accel': float(row['price_acceleration']),
                'mkt_slope': float(row['mkt_weighted_slope_2m']),
                'mkt_change': float(row['mkt_change_1m_pct']),
                'mkt_accel': float(row['mkt_acceleration']),
                'code': row['bond_code'],
                'time': row['time']
            })
        conn.commit()
    
    print(f"[完成] 回填 {len(df)} 行数据")
    
    # 输出统计
    print(f"\n[统计]")
    print(f"  加权斜率均值: {df['weighted_slope_2m'].mean():.6f}")
    print(f"  变化率均值: {df['change_1m_pct'].mean():.4f}%")
    print(f"  加速度均值: {df['price_acceleration'].mean():.6f}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='回填优化版斜率指标')
    parser.add_argument('--date', required=True, help='日期 YYYYMMDD')
    parser.add_argument('--table', help='表名，默认 monitor_zq_sssj_{date}')
    
    args = parser.parse_args()
    
    backfill_indicators(args.date, args.table)
