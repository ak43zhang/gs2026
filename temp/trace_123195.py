#!/usr/bin/env python3
"""以 123195 @ 10:42:48 为例追踪整个流程"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine("mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8")

BOND_CODE = '123195'
TICK_TIME = '10:42:48'

print(f"{'='*60}")
print(f"追踪: {BOND_CODE} @ {TICK_TIME}")
print(f"{'='*60}\n")

# ===== 1. 原始数据 =====
print("[1] 查询原始数据")
with engine.connect() as conn:
    df = pd.read_sql(text("""
        SELECT * FROM monitor_zq_sssj_20260710 
        WHERE bond_code = :code AND time = :t
    """), conn, params={'code': BOND_CODE, 't': TICK_TIME})

if df.empty:
    print(f"  ✗ 未找到 {BOND_CODE} @ {TICK_TIME} 的记录!")
    # 尝试查找附近时间
    with engine.connect() as conn:
        nearby = pd.read_sql(text("""
            SELECT time, bond_code, price, change_pct, amount, min1_change_pct, min1_amount, is_body_up, amount_rank
            FROM monitor_zq_sssj_20260710 
            WHERE bond_code = :code AND time BETWEEN '10:42:00' AND '10:43:00'
            ORDER BY time
        """), conn, params={'code': BOND_CODE})
    if not nearby.empty:
        print(f"  附近时间段的记录:")
        for _, row in nearby.iterrows():
            print(f"    time={row['time']} price={row['price']} change_pct={row['change_pct']} "
                  f"min1_change={row['min1_change_pct']} min1_amt={row['min1_amount']} "
                  f"is_body_up={row['is_body_up']} amount_rank={row['amount_rank']}")
    sys.exit(0)

row = df.iloc[0]
print(f"  ✓ 找到记录")
print(f"  bond_name: {row.get('bond_name')}")
print(f"  price: {row.get('price')}")
print(f"  change_pct: {row.get('change_pct')}")
print(f"  amount: {row.get('amount')}")
print(f"  min1_change_pct: {row.get('min1_change_pct')}")
print(f"  min1_amount: {row.get('min1_amount')}")
print(f"  is_body_up: {row.get('is_body_up')}")
print(f"  amount_rank: {row.get('amount_rank')}")
print(f"  slope_short: {row.get('slope_short')}")

# ===== 2. 逐条件判断 =====
print(f"\n[2] 逐条件判断")
conditions = [
    {'field': 'min1_change_pct', 'op': '>', 'value': 0.2},
    {'field': 'min1_change_pct', 'op': '<', 'value': 0.8},
    {'field': 'min1_amount', 'op': '>', 'value': 10000000},
    {'field': 'is_body_up', 'op': '>=', 'value': 0},
    {'field': 'amount_rank', 'op': '<=', 'value': 20},
]

all_pass = True
for c in conditions:
    field = c['field']
    op = c['op']
    val = c['value']
    actual = row.get(field)
    
    if op == '>': passed = actual > val
    elif op == '>=': passed = actual >= val
    elif op == '<': passed = actual < val
    elif op == '<=': passed = actual <= val
    elif op == '=': passed = actual == val
    else: passed = False
    
    status = '✓' if passed else '✗'
    print(f"  {status} {field} {op} {val}  (实际值: {actual})")
    if not passed:
        all_pass = False

print(f"\n  结论: {'全部通过 → 应该命中' if all_pass else '未全部通过 → 不应命中'}")

# ===== 3. 检查该tick全量数据的筛选结果 =====
print(f"\n[3] 该tick全量筛选（模拟API行为）")
with engine.connect() as conn:
    df_all = pd.read_sql(text("""
        SELECT * FROM monitor_zq_sssj_20260710 WHERE time = :t
    """), conn, params={'t': TICK_TIME})

print(f"  该tick总行数: {len(df_all)}")

# 应用条件
mask = pd.Series(True, index=df_all.index)
for c in conditions:
    field = c['field']
    op = c['op']
    val = float(c['value'])
    if field not in df_all.columns:
        print(f"  ✗ 字段 {field} 不存在!")
        continue
    if op == '>':      mask &= df_all[field] > val
    elif op == '>=':   mask &= df_all[field] >= val
    elif op == '<':    mask &= df_all[field] < val
    elif op == '<=':   mask &= df_all[field] <= val

hit = df_all[mask]
print(f"  满足所有条件: {len(hit)} 条")
if len(hit) > 0:
    print(f"  命中列表:")
    for _, r in hit.iterrows():
        print(f"    {r['bond_code']} {r['bond_name']} "
              f"min1_chg={r['min1_change_pct']} min1_amt={r['min1_amount']} "
              f"rank={r['amount_rank']} is_body_up={r['is_body_up']}")

# 检查123195是否在命中列表
if BOND_CODE in hit['bond_code'].values:
    print(f"\n  ★ {BOND_CODE} 在命中列表中!")
else:
    print(f"\n  ★ {BOND_CODE} 不在命中列表中 - 某个条件不满足")

# ===== 4. 检查quant_screen_hits是否有该记录 =====
print(f"\n[4] 检查 quant_screen_hits 是否有该记录")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT * FROM quant_screen_hits 
        WHERE trade_date = '20260710' AND bond_code = :code
        ORDER BY tick_time
    """), {'code': BOND_CODE})
    hits = result.fetchall()
    print(f"  今日该债券命中记录数: {len(hits)}")
    for h in hits[:5]:
        print(f"    tick={h.tick_time} status={h.signal_status}")

# ===== 5. 检查该时间点API是否被调用过 =====
print(f"\n[5] 检查10:42附近是否有任何命中记录")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT tick_time, bond_code, bond_name, entry_price 
        FROM quant_screen_hits 
        WHERE trade_date = '20260710' AND tick_time BETWEEN '104200' AND '104300'
        ORDER BY tick_time
        LIMIT 10
    """))
    nearby_hits = result.fetchall()
    print(f"  10:42-10:43时段命中记录: {len(nearby_hits)}")
    for h in nearby_hits:
        print(f"    {h[0]} {h[1]} {h[2]} price={h[3]}")

print(f"\n{'='*60}")
print("追踪完成")
