#!/usr/bin/env python3
"""完整追踪量化选债流程，定位断点"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine("mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8")

print("=" * 60)
print("量化选债流程诊断")
print("=" * 60)

# ===== 步骤1: 检查方案表结构 =====
print("\n[步骤1] 检查 quant_screen_schemes 表结构")
with engine.connect() as conn:
    result = conn.execute(text("DESCRIBE quant_screen_schemes"))
    cols = [row[0] for row in result]
    print(f"  字段: {cols}")
    has_use_realtime = 'use_realtime' in cols
    print(f"  use_realtime 字段: {'✓ 存在' if has_use_realtime else '✗ 不存在!'}")

# ===== 步骤2: 检查在用方案 =====
print("\n[步骤2] 检查在用方案")
with engine.connect() as conn:
    if has_use_realtime:
        result = conn.execute(text("""
            SELECT scheme_name, is_active, use_realtime, conditions_json
            FROM quant_screen_schemes 
            WHERE is_active = 1 AND use_realtime = 1
        """))
    else:
        result = conn.execute(text("""
            SELECT scheme_name, is_active, conditions_json
            FROM quant_screen_schemes 
            WHERE is_active = 1
        """))
    rows = result.fetchall()
    print(f"  在用方案数: {len(rows)}")
    for row in rows:
        print(f"    - {row[0]} (is_active={row[1]})")
        conditions = json.loads(row[-1]) if row[-1] else []
        print(f"      条件: {conditions}")

# ===== 步骤3: 检查数据获取 =====
print("\n[步骤3] 模拟 _get_current_sssj() 获取最新数据")
with engine.connect() as conn:
    # 获取最新时间点
    result = conn.execute(text("SELECT MAX(time) FROM monitor_zq_sssj_20260710"))
    latest_time = result.fetchone()[0]
    print(f"  最新tick时间: {latest_time}")
    
    if latest_time:
        # 获取该时间点数据
        df = pd.read_sql(text(f"SELECT * FROM monitor_zq_sssj_20260710 WHERE time = :t"),
                        conn, params={'t': str(latest_time)})
        print(f"  该tick数据行数: {len(df)}")
        print(f"  DataFrame列: {list(df.columns)}")
        
        # 检查关键字段的值
        key_fields = ['min1_change_pct', 'min1_amount', 'is_body_up', 'amount_rank']
        for field in key_fields:
            if field in df.columns:
                non_null = df[field].notna().sum()
                dtype = df[field].dtype
                sample_vals = df[field].dropna().head(3).tolist()
                print(f"    {field}: dtype={dtype}, 非空={non_null}/{len(df)}, 示例={sample_vals}")
            else:
                print(f"    {field}: ✗ 不存在!")

# ===== 步骤4: 模拟条件筛选 =====
print("\n[步骤4] 模拟条件筛选")
if rows and latest_time:
    conditions = json.loads(rows[0][-1]) if rows[0][-1] else []
    
    mask = pd.Series(True, index=df.index)
    for c in conditions:
        field = c.get('field', '')
        if field not in df.columns:
            print(f"  ✗ 字段 '{field}' 不在DataFrame中!")
            continue
        
        op = c.get('op', '>')
        val = float(c.get('value', 0))
        
        # 检查该字段的NaN情况
        nan_count = df[field].isna().sum()
        if nan_count > 0:
            print(f"  ⚠ 字段 '{field}' 有 {nan_count}/{len(df)} 个NaN值")
        
        if op == '>':      sub_mask = df[field] > val
        elif op == '>=':   sub_mask = df[field] >= val
        elif op == '<':    sub_mask = df[field] < val
        elif op == '<=':   sub_mask = df[field] <= val
        elif op == '=':    sub_mask = df[field] == val
        elif op == '!=':   sub_mask = df[field] != val
        elif op == 'between':
            val2 = float(c.get('value2', val))
            sub_mask = (df[field] >= val) & (df[field] <= val2)
        else:
            sub_mask = pd.Series(True, index=df.index)
        
        before_count = mask.sum()
        mask &= sub_mask
        after_count = mask.sum()
        print(f"  条件: {field} {op} {val} → 剩余: {before_count} → {after_count}")
    
    hit = df[mask]
    print(f"\n  最终命中: {len(hit)} 条")
    if len(hit) > 0:
        print(f"  前5条:")
        for _, row in hit.head(5).iterrows():
            print(f"    {row.get('bond_code')} {row.get('bond_name')} "
                  f"price={row.get('price')} change={row.get('change_pct')}%")

# ===== 步骤5: 检查 quant_screen_hits 今日数据 =====
print("\n[步骤5] 检查 quant_screen_hits 今日数据")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT COUNT(*) FROM quant_screen_hits WHERE trade_date = '20260710'
    """))
    count = result.fetchone()[0]
    print(f"  今日命中记录数: {count}")
    
    if count > 0:
        result = conn.execute(text("""
            SELECT tick_time, bond_code, bond_name, entry_price, signal_status
            FROM quant_screen_hits 
            WHERE trade_date = '20260710'
            ORDER BY id DESC LIMIT 5
        """))
        print(f"  最新5条:")
        for row in result:
            print(f"    time={row[0]} {row[1]} {row[2]} price={row[3]} status={row[4]}")

# ===== 步骤6: 检查Web服务是否在运行 =====
print("\n[步骤6] 测试API是否可达")
try:
    import requests
    r = requests.post('http://localhost:8080/api/monitor/quant-screen', 
                     json={}, timeout=5)
    print(f"  API状态码: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  返回: success={data.get('success')}, matches={len(data.get('matches', []))}")
        if data.get('error'):
            print(f"  错误: {data['error']}")
        if data.get('message'):
            print(f"  消息: {data['message']}")
    else:
        print(f"  响应: {r.text[:200]}")
except Exception as e:
    print(f"  ✗ API不可达: {e}")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
