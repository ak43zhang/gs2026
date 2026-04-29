#!/usr/bin/env python3
"""
检查填充进度
"""
from sqlalchemy import create_engine, text
import time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("检查2026-04-29填充进度")
print("=" * 80)

table_name = "monitor_gp_sssj_20260429"

with engine.connect() as conn:
    # 总体统计
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
    """))
    
    row = result.fetchone()
    total = row[0]
    main_nonzero = row[1]
    cum_nonzero = row[2]
    
    print(f"\n总体进度:")
    print(f"  总记录: {total:,}")
    print(f"  已填充main_net_amount: {main_nonzero:,} ({main_nonzero/total*100:.1f}%)")
    print(f"  已填充cumulative_main_net: {cum_nonzero:,} ({cum_nonzero/total*100:.1f}%)")
    
    # 按小时统计
    result = conn.execute(text(f"""
        SELECT 
            SUBSTRING(time, 1, 2) as hour,
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
        GROUP BY SUBSTRING(time, 1, 2)
        ORDER BY hour
    """))
    
    print(f"\n按小时统计:")
    print(f"  小时 | 总记录 | main_net | cumulative_main_net")
    print(f"  -----|--------|----------|-------------------")
    for row in result.fetchall():
        hour = row[0]
        total_hour = row[1]
        main = row[2]
        cum = row[3]
        print(f"  {hour}:00 | {total_hour:6,} | {main:8,} ({main/total_hour*100:5.1f}%) | {cum:8,} ({cum/total_hour*100:5.1f}%)")
    
    # Top 10
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            short_name,
            MAX(cumulative_main_net) as max_cumulative
        FROM {table_name}
        WHERE cumulative_main_net != 0
        GROUP BY stock_code, short_name
        ORDER BY ABS(MAX(cumulative_main_net)) DESC
        LIMIT 10
    """))
    
    print(f"\nTop 10 累计主力净额:")
    for i, row in enumerate(result.fetchall(), 1):
        print(f"  {i}. {row[0]} {row[1]}: {row[2]:,.0f}")

print(f"\n{'='*80}")
