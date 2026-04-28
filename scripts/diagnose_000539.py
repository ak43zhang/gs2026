#!/usr/bin/env python3
"""
诊断 000539 为什么 1312 条满足门槛的记录只有 39 条有主力净额
"""
from sqlalchemy import create_engine, text
from datetime import time as dt_time
import pandas as pd
import numpy as np

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    df = pd.read_sql("""
        SELECT stock_code, short_name, price, volume, amount, change_pct, time
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000539'
        ORDER BY time
    """, conn)

df['price'] = pd.to_numeric(df['price'], errors='coerce')
df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
df['change_pct'] = pd.to_numeric(df['change_pct'], errors='coerce')

df = df.sort_values('time').reset_index(drop=True)

# 计算周期变化
df['delta_amount'] = df['amount'].diff().fillna(0)
df['delta_volume'] = df['volume'].diff().fillna(0)
df['delta_change_pct'] = df['change_pct'].diff().fillna(0)

# 当日高低
day_high = df['price'].max()
day_low = df['price'].min()
price_range = day_high - day_low if day_high > day_low else 1.0
df['price_position'] = ((df['price'] - day_low) / price_range).clip(0, 1)

# 量能比
median_vol = df['delta_volume'].median()
if median_vol <= 0:
    median_vol = 20000
df['volume_ratio'] = df['delta_volume'] / median_vol

print(f"=== 000539 诊断分析 ===")
print(f"总记录: {len(df)}")
print(f"当日价格: high={day_high:.2f}, low={day_low:.2f}, range={price_range:.2f}")
print(f"delta_volume median: {median_vol:,.0f}")
print()

# 门槛筛选
mask_threshold = (df['delta_amount'] >= 300000) & (df['delta_volume'] >= 20000)
df_thresh = df[mask_threshold].copy()
print(f"满足门槛的记录: {len(df_thresh)}")
print()

# ======== 分析 classify_behavior 的每个条件 ========
print("=" * 80)
print("classify_behavior 条件分析（对 1312 条满足门槛的记录）")
print("=" * 80)
print()

# 条件用到的变量分布
print("--- delta_change_pct 分布 ---")
print(df_thresh['delta_change_pct'].describe())
print()
print("分位数:")
for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
    v = df_thresh['delta_change_pct'].quantile(p/100)
    print(f"  {p}%: {v:.4f}")
print()

print("--- price_position 分布 ---")
print(df_thresh['price_position'].describe())
print()

print("--- volume_ratio 分布 ---")
print(df_thresh['volume_ratio'].describe())
print()

# ======== 逐条件统计命中数 ========
print("=" * 80)
print("各场景命中统计")
print("=" * 80)
print()

# 场景1: 拉高出货
c1 = (df_thresh['price_position'] >= 0.98) & (df_thresh['delta_change_pct'] >= 1.0) & (df_thresh['volume_ratio'] >= 5)
print(f"场景1 拉高出货 (pos>=0.98 AND pct>=1.0 AND vol_ratio>=5): {c1.sum()} 条")
# 分别看每个子条件
c1a = df_thresh['price_position'] >= 0.98
c1b = df_thresh['delta_change_pct'] >= 1.0
c1c = df_thresh['volume_ratio'] >= 5
print(f"  子条件: pos>=0.98={c1a.sum()}, pct>=1.0={c1b.sum()}, vol_ratio>=5={c1c.sum()}")
print()

# 场景2: 真正拉升
c2 = (df_thresh['price_position'] <= 0.3) & (df_thresh['delta_change_pct'] >= 0.3) & (df_thresh['volume_ratio'] >= 2)
print(f"场景2 真正拉升 (pos<=0.3 AND pct>=0.3 AND vol_ratio>=2): {c2.sum()} 条")
c2a = df_thresh['price_position'] <= 0.3
c2b = df_thresh['delta_change_pct'] >= 0.3
c2c = df_thresh['volume_ratio'] >= 2
print(f"  子条件: pos<=0.3={c2a.sum()}, pct>=0.3={c2b.sum()}, vol_ratio>=2={c2c.sum()}")
print()

# 场景3: 打压吸筹
c3 = (df_thresh['price_position'] <= 0.3) & (df_thresh['delta_change_pct'] <= -0.5) & (df_thresh['volume_ratio'] >= 2)
print(f"场景3 打压吸筹 (pos<=0.3 AND pct<=-0.5 AND vol_ratio>=2): {c3.sum()} 条")
c3b = df_thresh['delta_change_pct'] <= -0.5
print(f"  子条件: pos<=0.3={c2a.sum()}, pct<=-0.5={c3b.sum()}, vol_ratio>=2={c2c.sum()}")
print()

# 场景4: 恐慌抛售
c4 = (df_thresh['price_position'] >= 0.9) & (df_thresh['delta_change_pct'] <= -0.5) & (df_thresh['volume_ratio'] >= 2)
print(f"场景4 恐慌抛售 (pos>=0.9 AND pct<=-0.5 AND vol_ratio>=2): {c4.sum()} 条")
c4a = df_thresh['price_position'] >= 0.9
print(f"  子条件: pos>=0.9={c4a.sum()}, pct<=-0.5={c3b.sum()}, vol_ratio>=2={c2c.sum()}")
print()

# 场景5: 疑似拉升 (9:30-10:00)
def in_early(t):
    parts = t.split(':')
    return dt_time(9, 30) <= dt_time(int(parts[0]), int(parts[1])) <= dt_time(10, 0)
c5_time = df_thresh['time'].apply(in_early)
c5 = c5_time & (df_thresh['volume_ratio'] >= 2) & (df_thresh['delta_change_pct'] >= 0.3)
print(f"场景5 疑似拉升 (9:30-10:00 AND vol>=2 AND pct>=0.3): {c5.sum()} 条")
print(f"  子条件: 时间在9:30-10:00={c5_time.sum()}, vol>=2={c2c.sum()}, pct>=0.3={c2b.sum()}")
print()

# 场景6: 疑似出货 (14:30-15:00)
def in_late(t):
    parts = t.split(':')
    return dt_time(14, 30) <= dt_time(int(parts[0]), int(parts[1])) <= dt_time(15, 0)
c6_time = df_thresh['time'].apply(in_late)
c6 = c6_time & (df_thresh['volume_ratio'] >= 2) & (df_thresh['delta_change_pct'] >= 0.3)
print(f"场景6 疑似出货 (14:30-15:00 AND vol>=2 AND pct>=0.3): {c6.sum()} 条")
print(f"  子条件: 时间在14:30-15:00={c6_time.sum()}")
print()

# 兜底逻辑
c_fallback_pos = df_thresh['delta_change_pct'] >= 0.5
c_fallback_neg = df_thresh['delta_change_pct'] <= -0.5
c_fallback_zero = (df_thresh['delta_change_pct'] > -0.5) & (df_thresh['delta_change_pct'] < 0.5)
print(f"兜底 不确定(pct>=0.5, direction=0.3): {c_fallback_pos.sum()} 条")
print(f"兜底 不确定(pct<=-0.5, direction=-0.3): {c_fallback_neg.sum()} 条")
print(f"兜底 不确定(|pct|<0.5, direction=0 -> net=0): {c_fallback_zero.sum()} 条 <<<< 这就是被过滤掉的！")
print()

# 被前面场景命中的
any_scene = c1 | c2 | c3 | c4 | c5 | c6
not_any_scene = ~any_scene
print(f"命中场景1-6: {any_scene.sum()} 条")
print(f"未命中场景1-6（进入兜底）: {not_any_scene.sum()} 条")
print()

# 进入兜底的记录中
df_fallback = df_thresh[not_any_scene]
fb_pos = (df_fallback['delta_change_pct'] >= 0.5).sum()
fb_neg = (df_fallback['delta_change_pct'] <= -0.5).sum()
fb_zero = ((df_fallback['delta_change_pct'] > -0.5) & (df_fallback['delta_change_pct'] < 0.5)).sum()
print(f"兜底记录中:")
print(f"  pct>=0.5 (direction=0.3, 有净额): {fb_pos} 条")
print(f"  pct<=-0.5 (direction=-0.3, 有净额): {fb_neg} 条")
print(f"  |pct|<0.5 (direction=0, 净额为0): {fb_zero} 条 <<<< 这些满足门槛但净额为0！")
print()

print("=" * 80)
print("结论: 1312条满足门槛 -> 进入classify_behavior")
print(f"  场景1-6命中: {any_scene.sum()} 条 -> 有方向，有净额")
print(f"  兜底有方向: {fb_pos + fb_neg} 条 -> 有净额（但方向弱）")
print(f"  兜底无方向: {fb_zero} 条 -> direction=0 -> 净额=0 <<<< 被丢弃的！")
total_with_net = any_scene.sum() + fb_pos + fb_neg
print(f"  合计有净额: {total_with_net} 条")
print(f"  合计无净额: {fb_zero} 条")
print()

# ======== 更深层的问题分析 ========
print("=" * 80)
print("深层问题分析")
print("=" * 80)
print()
print("delta_change_pct 是什么？")
print("  = change_pct.diff() = 涨跌幅的变化（不是涨跌幅本身）")
print("  例如：上一tick涨2.0%，当前tick涨2.1%，delta_change_pct = 0.1%")
print("  大部分tick之间涨跌幅变化很小（<0.5%），所以大量记录被归为direction=0")
print()
print("这是核心问题：")
print("  3秒内涨跌幅变化通常在 -0.5% ~ 0.5% 之间")
print("  导致绝大多数满足门槛的记录被判为 direction=0")
print("  只有涨跌幅剧烈变化（>0.5%/3秒）的记录才有净额")
