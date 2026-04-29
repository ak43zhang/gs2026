#!/usr/bin/env python3
"""全面分析000925问题"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 70)
print("000925 全面分析")
print("=" * 70)

with engine.connect() as conn:
    # 1. 获取全天的价格变化
    print("\n【全天价格变化】")
    print("-" * 70)
    
    df = pd.read_sql("""
        SELECT time, price, change_pct, main_net_amount, cumulative_main_net
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        ORDER BY time
    """, conn)
    
    # 关键时间点
    key_times = ['09:30:00', '10:00:00', '11:00:00', '13:00:00', '14:00:00', '14:30:00', '14:57:00', '15:00:00']
    
    print(f"总记录数: {len(df)}")
    print(f"\n关键时间点数据:")
    print(f"{'时间':<12} {'价格':<8} {'涨跌幅':<10} {'主力净额':<15} {'累计净额':<15}")
    print("-" * 70)
    
    for time_str in key_times:
        row = df[df['time'] == time_str]
        if not row.empty:
            r = row.iloc[0]
            print(f"{r['time']:<12} {r['price']:<8} {r['change_pct']:<10.2f} {r['main_net_amount']:<15.0f} {r['cumulative_main_net']:<15.0f}")
    
    # 2. 分析主力净额问题
    print("\n\n【主力净额分析】")
    print("-" * 70)
    
    # 统计
    total_records = len(df)
    non_zero_main_net = len(df[df['main_net_amount'] != 0])
    positive_main_net = len(df[df['main_net_amount'] > 0])
    negative_main_net = len(df[df['main_net_amount'] < 0])
    
    total_main_net = df['main_net_amount'].sum()
    max_main_net = df['main_net_amount'].max()
    min_main_net = df['main_net_amount'].min()
    
    print(f"总记录数: {total_records}")
    print(f"有主力净额的记录: {non_zero_main_net} ({non_zero_main_net/total_records*100:.1f}%)")
    print(f"净流入次数: {positive_main_net}")
    print(f"净流出次数: {negative_main_net}")
    print(f"主力净额总和: {total_main_net:,.0f} 元")
    print(f"最大单笔净流入: {max_main_net:,.0f} 元")
    print(f"最大单笔净流出: {min_main_net:,.0f} 元")
    
    # 3. 分析为什么跌但主力净额为正
    print("\n\n【问题2分析：为什么跌但主力净额为正？】")
    print("-" * 70)
    
    # 找出价格下跌但主力净额为正的记录
    df_down_but_inflow = df[(df['change_pct'] < -3) & (df['main_net_amount'] > 0)]
    
    print(f"跌>3%但主力净流入的记录: {len(df_down_but_inflow)} 条")
    
    if len(df_down_but_inflow) > 0:
        print("\n前10条示例:")
        print(df_down_but_inflow[['time', 'price', 'change_pct', 'main_net_amount']].head(10).to_string(index=False))
    
    # 4. 分析价格区间和主力行为
    print("\n\n【价格区间分析】")
    print("-" * 70)
    
    # 早盘（9:30-11:30）
    morning = df[df['time'] <= '11:30:00']
    # 午盘（13:00-15:00）
    afternoon = df[df['time'] >= '13:00:00']
    
    print(f"早盘 (9:30-11:30):")
    print(f"  价格区间: {morning['price'].min()} - {morning['price'].max()}")
    print(f"  主力净额总和: {morning['main_net_amount'].sum():,.0f} 元")
    
    print(f"\n午盘 (13:00-15:00):")
    print(f"  价格区间: {afternoon['price'].min()} - {afternoon['price'].max()}")
    print(f"  主力净额总和: {afternoon['main_net_amount'].sum():,.0f} 元")
    
    # 5. 检查累计净额字段
    print("\n\n【累计主力净额字段检查】")
    print("-" * 70)
    
    non_zero_cumulative = len(df[df['cumulative_main_net'] != 0])
    print(f"有累计净额的记录: {non_zero_cumulative} ({non_zero_cumulative/total_records*100:.2f}%)")
    
    if non_zero_cumulative == 0:
        print("【问题】累计净额字段全为0！")
        print("原因：新字段尚未填充数据，需要运行填充脚本")
    else:
        print(f"累计净额范围: {df['cumulative_main_net'].min():,.0f} ~ {df['cumulative_main_net'].max():,.0f}")

print("\n" + "=" * 70)
print("分析完成")
