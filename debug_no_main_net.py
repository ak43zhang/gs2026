#!/usr/bin/env python3
"""
排查主力净额没有数据的问题根源
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("排查主力净额没有数据的问题根源")
print("=" * 80)

date = '20260428'
table_name = f"monitor_gp_sssj_{date}"

# 1. 检查表结构
print("\n【1】检查表结构...")
with engine.connect() as conn:
    result = conn.execute(text(f"DESCRIBE {table_name}"))
    columns = [row[0] for row in result.fetchall()]
    print(f"  字段: {columns}")
    
    has_cumulative = 'cumulative_main_net' in columns
    has_main_net = 'main_net_amount' in columns
    print(f"  cumulative_main_net: {'存在' if has_cumulative else '缺失'}")
    print(f"  main_net_amount: {'存在' if has_main_net else '缺失'}")

# 2. 检查数据分布
print("\n【2】检查数据分布...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount IS NULL THEN 1 ELSE 0 END) as main_null,
            SUM(CASE WHEN main_net_amount = 0 THEN 1 ELSE 0 END) as main_zero,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
            SUM(CASE WHEN cumulative_main_net IS NULL THEN 1 ELSE 0 END) as cum_null,
            SUM(CASE WHEN cumulative_main_net = 0 THEN 1 ELSE 0 END) as cum_zero,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
    """))
    
    row = result.fetchone()
    print(f"  总记录: {row[0]:,}")
    print(f"  main_net_amount: NULL={row[1]}, 零={row[2]}, 非零={row[3]}")
    print(f"  cumulative_main_net: NULL={row[4]}, 零={row[5]}, 非零={row[6]}")

# 3. 检查15:00:00时间点的数据
print("\n【3】检查15:00:00时间点数据...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
        WHERE time = '15:00:00'
    """))
    
    row = result.fetchone()
    print(f"  15:00:00总记录: {row[0]}")
    print(f"  非零main_net_amount: {row[1]}")
    print(f"  非零cumulative_main_net: {row[2]}")

# 4. 检查上攻排行的股票
print("\n【4】检查上攻排行股票的主力净额...")
with engine.connect() as conn:
    # 获取上攻排行Top 10股票
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            short_name,
            main_net_amount,
            cumulative_main_net
        FROM {table_name}
        WHERE time = '15:00:00'
        ORDER BY ABS(COALESCE(cumulative_main_net, main_net_amount, 0)) DESC
        LIMIT 10
    """))
    
    rows = result.fetchall()
    print(f"  Top 10 主力净额股票:")
    for row in rows:
        print(f"    {row[0]} {row[1]}: main={row[2]}, cum={row[3]}")

# 5. 测试前端查询函数
print("\n【5】测试前端查询函数...")
from gs2026.dashboard2.routes.monitor import _get_change_pct_and_main_net_batch

test_codes = ['300540', '300243', '000001', '000002', '000063']
change_pct_map, main_net_map = _get_change_pct_and_main_net_batch(date, '15:00:00', test_codes)

print(f"  查询结果:")
for code in test_codes:
    change_pct = change_pct_map.get(code, '-')
    main_net = main_net_map.get(code, 'N/A')
    print(f"    {code}: 涨跌幅={change_pct}, 主力净额={main_net}")

# 6. 检查Redis数据
print("\n【6】检查Redis数据...")
try:
    from gs2026.utils import redis_util
    redis_key = f"{table_name}:15:00:00"
    df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
    
    if df is not None and not df.empty:
        print(f"  Redis数据存在，记录数: {len(df)}")
        print(f"  列: {df.columns.tolist()}")
        if 'cumulative_main_net' in df.columns:
            non_zero = (df['cumulative_main_net'] != 0).sum()
            print(f"  非零cumulative_main_net: {non_zero}")
        else:
            print(f"  cumulative_main_net字段不存在！")
    else:
        print(f"  Redis数据不存在！")
except Exception as e:
    print(f"  Redis检查失败: {e}")

print(f"\n{'='*80}")
