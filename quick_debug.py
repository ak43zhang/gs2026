#!/usr/bin/env python3
"""
快速排查
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("快速排查主力净额问题")
print("=" * 80)

table_name = "monitor_gp_sssj_20260428"

# 1. 检查数据
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
    print(f"\n15:00:00数据:")
    print(f"  总记录: {row[0]}")
    print(f"  非零main_net_amount: {row[1]}")
    print(f"  非零cumulative_main_net: {row[2]}")

# 2. 显示有数据的股票
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT stock_code, short_name, main_net_amount, cumulative_main_net
        FROM {table_name}
        WHERE time = '15:00:00' AND cumulative_main_net != 0
        LIMIT 5
    """))
    
    print(f"\n有累计值的Top 5:")
    for row in result.fetchall():
        print(f"  {row[0]} {row[1]}: main={row[2]:.0f}, cum={row[3]:.0f}")

print("\n" + "=" * 80)
