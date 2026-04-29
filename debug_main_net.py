#!/usr/bin/env python3
"""
排查主力净额为空的原因
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("排查主力净额为空的原因")
print("=" * 80)

# 测试参数
date = '20260428'
time_str = '15:00:00'
stock_codes = ['000001', '000002', '000063', '000333', '000538']

codes_str = ','.join([f"'{c}'" for c in stock_codes])
table_name = f"monitor_gp_sssj_{date}"

print(f"\n【1】检查表结构...")
with engine.connect() as conn:
    result = conn.execute(text(f"DESCRIBE {table_name}"))
    columns = [row[0] for row in result.fetchall()]
    print(f"  表字段: {columns}")
    
    # 检查是否有cumulative_main_net字段
    if 'cumulative_main_net' in columns:
        print(f"  [OK] cumulative_main_net 字段存在")
    else:
        print(f"  [FAIL] cumulative_main_net 字段不存在！")

print(f"\n【2】查询样本数据...")
query = f"""
    SELECT stock_code, time, price, change_pct, main_net_amount, cumulative_main_net
    FROM {table_name}
    WHERE time = '{time_str}' AND stock_code IN ({codes_str})
    LIMIT 10
"""

with engine.connect() as conn:
    df = pd.read_sql(query, conn)
    print(f"  查询结果:\n{df}")

print(f"\n【3】检查cumulative_main_net字段值...")
query = f"""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN cumulative_main_net IS NULL THEN 1 ELSE 0 END) as null_count,
        SUM(CASE WHEN cumulative_main_net = 0 THEN 1 ELSE 0 END) as zero_count,
        SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as non_zero_count
    FROM {table_name}
    WHERE time = '{time_str}'
"""

with engine.connect() as conn:
    result = conn.execute(text(query))
    row = result.fetchone()
    print(f"  总记录: {row[0]}")
    print(f"  NULL值: {row[1]}")
    print(f"  零值: {row[2]}")
    print(f"  非零值: {row[3]}")

print(f"\n【4】检查main_net_amount字段值...")
query = f"""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN main_net_amount IS NULL THEN 1 ELSE 0 END) as null_count,
        SUM(CASE WHEN main_net_amount = 0 THEN 1 ELSE 0 END) as zero_count,
        SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as non_zero_count
    FROM {table_name}
    WHERE time = '{time_str}'
"""

with engine.connect() as conn:
    result = conn.execute(text(query))
    row = result.fetchone()
    print(f"  总记录: {row[0]}")
    print(f"  NULL值: {row[1]}")
    print(f"  零值: {row[2]}")
    print(f"  非零值: {row[3]}")

print(f"\n【5】测试实际查询...")
from gs2026.dashboard2.routes.monitor import _get_change_pct_and_main_net_batch

change_pct_map, main_net_map = _get_change_pct_and_main_net_batch(date, time_str, stock_codes)

print(f"  返回的main_net_map:")
for code in stock_codes:
    value = main_net_map.get(code, 'N/A')
    print(f"    {code}: {value}")

print(f"\n{'='*80}")
