#!/usr/bin/env python3
"""
测试MySQL查询性能
"""
import time
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("MySQL查询性能测试")
print("=" * 80)

# 测试参数
date = '20260428'
time_str = '15:00:00'
stock_codes = ['000001', '000002', '000063', '000333', '000538', '000568', 
               '000625', '000651', '000725', '000768', '000858', '000895',
               '002001', '002007', '002024', '002027', '002142', '002230',
               '002236', '002271', '002304', '002352', '002415', '002460',
               '002475', '002594', '002714', '002812', '003816', '300003',
               '300014', '300015', '300033', '300059', '300122', '300124',
               '300274', '300408', '300413', '300433', '300498', '300750',
               '600000', '600009', '600016', '600028', '600030', '600031',
               '600036', '600048', '600050', '600104', '600276', '600309',
               '600406', '600436', '600438', '600519', '600585', '600588']

codes_str = ','.join([f"'{c}'" for c in stock_codes])
table_name = f"monitor_gp_sssj_{date}"

# 测试1: 单条查询（优化后）
print("\n【测试1】单条查询（优化后）...")
query1 = f"""
    SELECT stock_code, change_pct, main_net_amount, cumulative_main_net
    FROM {table_name}
    WHERE time = '{time_str}' AND stock_code IN ({codes_str})
"""

start_time = time.time()
with engine.connect() as conn:
    result = conn.execute(text(query1))
    rows = result.fetchall()
elapsed1 = time.time() - start_time

print(f"  耗时: {elapsed1:.3f}秒")
print(f"  返回: {len(rows)}条")

# 测试2: 累计查询（优化前）
print("\n【测试2】累计查询（优化前）...")
query2 = f"""
    SELECT stock_code, SUM(main_net_amount) as cumulative_main_net
    FROM {table_name}
    WHERE time <= '{time_str}' AND stock_code IN ({codes_str})
    GROUP BY stock_code
"""

start_time = time.time()
with engine.connect() as conn:
    result = conn.execute(text(query2))
    rows = result.fetchall()
elapsed2 = time.time() - start_time

print(f"  耗时: {elapsed2:.3f}秒")
print(f"  返回: {len(rows)}条")

# 对比
print(f"\n{'='*80}")
print("性能对比:")
print(f"  优化后（单条）: {elapsed1:.3f}秒")
print(f"  优化前（累计）: {elapsed2:.3f}秒")
if elapsed2 > 0:
    print(f"  提升: {elapsed2/elapsed1:.1f}倍")
print(f"{'='*80}")
