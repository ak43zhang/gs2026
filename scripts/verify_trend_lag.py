#!/usr/bin/env python3
"""
验证方案B的"趋势滞后"问题
用 000539 实际数据模拟：涨了8%后开始下跌的场景
"""
from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    df = pd.read_sql("""
        SELECT time, price, change_pct, amount, volume
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000539'
        ORDER BY time
    """, conn)

df['price'] = pd.to_numeric(df['price'], errors='coerce')
df['change_pct'] = pd.to_numeric(df['change_pct'], errors='coerce')
df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

df['delta_amount'] = df['amount'].diff().fillna(0)
df['delta_change_pct'] = df['change_pct'].diff().fillna(0)
df['price_diff'] = df['price'].diff().fillna(0)

# 找下午冲高回落的区间 (14:17 - 14:30)
mask = (df['time'] >= '14:15:00') & (df['time'] <= '14:30:00') & (df['delta_amount'] >= 300000)
df_window = df[mask].copy()

print("=== 000539 冲高回落区间 (14:15-14:30) 大额交易 ===")
print()
print(f"{'time':<12} {'price':>7} {'chg_pct':>8} {'delta_amt':>14} {'price_diff':>10} {'delta_chg':>10}")
print("-" * 70)

for _, r in df_window.iterrows():
    print(f"{r['time']:<12} {r['price']:>7.2f} {r['change_pct']:>7.2f}% {r['delta_amount']:>13,.0f} "
          f"{r['price_diff']:>9.2f} {r['delta_change_pct']:>9.2f}%")

print()
print("=== 方案B会怎么判断？===")
print()
for _, r in df_window.iterrows():
    chg = r['change_pct']
    delta_chg = r['delta_change_pct']
    
    # 方案B的趋势评分
    if chg >= 3.0: trend = 1.0
    elif chg >= 1.0: trend = 0.7
    elif chg >= 0.0: trend = 0.3
    elif chg >= -1.0: trend = -0.3
    elif chg >= -3.0: trend = -0.7
    else: trend = -1.0
    
    # 方案B的加速度评分
    if delta_chg >= 0.3: accel = 1.0
    elif delta_chg >= 0.0: accel = 0.3
    elif delta_chg >= -0.3: accel = -0.3
    else: accel = -1.0
    
    direction_b = trend * 0.7 + accel * 0.3
    
    # 价格变化法
    if r['price_diff'] > 0: direction_price = 1.0
    elif r['price_diff'] < 0: direction_price = -1.0
    else: direction_price = 0.0
    
    label_b = "BUY" if direction_b > 0 else ("SELL" if direction_b < 0 else "FLAT")
    label_p = "BUY" if direction_price > 0 else ("SELL" if direction_price < 0 else "FLAT")
    
    correct = ""
    if r['price_diff'] < 0 and direction_b > 0:
        correct = " << WRONG! price falling but B says BUY"
    elif r['price_diff'] > 0 and direction_b < 0:
        correct = " << WRONG! price rising but B says SELL"
    
    print(f"  {r['time']}: chg={chg:>6.2f}%, delta={delta_chg:>6.2f}%, "
          f"price_diff={r['price_diff']:>5.2f} | "
          f"B: trend={trend:>4.1f} accel={accel:>4.1f} dir={direction_b:>5.2f}({label_b}) | "
          f"Price: dir={direction_price:>4.1f}({label_p}){correct}")

print()
print("=== price_diff 分布统计（全天满足门槛的记录）===")
mask_all = (df['delta_amount'] >= 300000) & (df['delta_volume'] >= 20000)
df_all = df[mask_all]

total = len(df_all)
up = (df_all['price_diff'] > 0).sum()
down = (df_all['price_diff'] < 0).sum()
flat = (df_all['price_diff'] == 0).sum()
print(f"Total: {total}")
print(f"Price UP:   {up} ({up/total*100:.1f}%)")
print(f"Price DOWN: {down} ({down/total*100:.1f}%)")
print(f"Price FLAT: {flat} ({flat/total*100:.1f}%)")
