#!/usr/bin/env python3
"""分析000925主力净额方向问题"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 70)
print("000925 主力净额方向分析")
print("=" * 70)

with engine.connect() as conn:
    # 1. 获取有主力净额的记录
    df = pd.read_sql("""
        SELECT time, price, change_pct, main_net_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND main_net_amount != 0
        ORDER BY time
    """, conn)
    
    print(f"\n有主力净额的记录: {len(df)} 条")
    
    # 2. 分析方向
    df['price_diff'] = df['price'].astype(float).diff()
    df['change_diff'] = df['change_pct'].astype(float).diff()
    
    # 分类
    price_up_main_in = len(df[(df['price_diff'] > 0) & (df['main_net_amount'] > 0)])
    price_up_main_out = len(df[(df['price_diff'] > 0) & (df['main_net_amount'] < 0)])
    price_down_main_in = len(df[(df['price_diff'] < 0) & (df['main_net_amount'] > 0)])
    price_down_main_out = len(df[(df['price_diff'] < 0) & (df['main_net_amount'] < 0)])
    price_flat_main_in = len(df[(df['price_diff'] == 0) & (df['main_net_amount'] > 0)])
    price_flat_main_out = len(df[(df['price_diff'] == 0) & (df['main_net_amount'] < 0)])
    
    print("\n价格变化与主力方向关系:")
    print(f"  价格上涨 + 主力流入: {price_up_main_in} 条")
    print(f"  价格上涨 + 主力流出: {price_up_main_out} 条")
    print(f"  价格下跌 + 主力流入: {price_down_main_in} 条  <-- 异常！")
    print(f"  价格下跌 + 主力流出: {price_down_main_out} 条")
    print(f"  价格不变 + 主力流入: {price_flat_main_in} 条")
    print(f"  价格不变 + 主力流出: {price_flat_main_out} 条")
    
    # 3. 找出典型的"跌但主力流入"记录
    print("\n\n【典型问题记录】价格下跌但主力净流入:")
    print("-" * 70)
    
    problem_records = df[(df['price_diff'] < -0.01) & (df['main_net_amount'] > 1000000)].head(10)
    
    if len(problem_records) > 0:
        print(f"{'时间':<12} {'价格':<8} {'价格变化':<10} {'涨跌幅':<10} {'主力净额':<15}")
        print("-" * 70)
        for _, row in problem_records.iterrows():
            print(f"{row['time']:<12} {row['price']:<8} {row['price_diff']:<10.2f} {row['change_pct']:<10.2f} {row['main_net_amount']:<15.0f}")
    
    # 4. 分析原因
    print("\n\n【原因分析】")
    print("-" * 70)
    
    print("1. Tick价格变化法逻辑:")
    print("   price_diff = price_now - price_prev")
    print("   如果 price_diff > 0 → direction = +1 (买入)")
    print("   如果 price_diff < 0 → direction = -1 (卖出)")
    print()
    
    print("2. 问题场景:")
    print("   - 股票从高位回落时，当前tick价格仍可能高于上一tick")
    print("   - 例如: 10.00 → 9.80 → 9.60")
    print("   - 在 9.80 这个tick，price_diff = -0.20 (下跌)，direction = -1")
    print("   - 但如果 9.80 → 9.81，price_diff = +0.01 (微涨)，direction = +1")
    print("   - 此时股票整体仍在下跌通道，但单tick显示主力流入")
    print()
    
    print("3. 000925全天走势:")
    print("   - 早盘低开: 10.00 → 9.59 (大跌)")
    print("   - 但过程中有反弹: 9.59 → 9.76 (反弹)")
    print("   - 反弹时的tick产生主力流入信号")
    print("   - 整体下跌，但反弹段的主力流入被累计")
    
    # 5. 计算各阶段主力净额
    print("\n\n【分阶段主力净额】")
    print("-" * 70)
    
    df_all = pd.read_sql("""
        SELECT time, price, change_pct, main_net_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        ORDER BY time
    """, conn)
    
    # 早盘大跌阶段 (9:30-10:00)
    morning_drop = df_all[df_all['time'] <= '10:00:00']
    # 反弹阶段 (10:00-11:30)
    rebound = df_all[(df_all['time'] > '10:00:00') & (df_all['time'] <= '11:30:00')]
    # 午盘 (13:00-15:00)
    afternoon = df_all[df_all['time'] >= '13:00:00']
    
    print(f"早盘大跌 (9:30-10:00): 价格 {morning_drop['price'].min()}~{morning_drop['price'].max()}, 主力净额 {morning_drop['main_net_amount'].sum():,.0f}")
    print(f"反弹阶段 (10:00-11:30): 价格 {rebound['price'].min()}~{rebound['price'].max()}, 主力净额 {rebound['main_net_amount'].sum():,.0f}")
    print(f"午盘震荡 (13:00-15:00): 价格 {afternoon['price'].min()}~{afternoon['price'].max()}, 主力净额 {afternoon['main_net_amount'].sum():,.0f}")

print("\n" + "=" * 70)
print("分析完成")
