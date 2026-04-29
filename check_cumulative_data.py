#!/usr/bin/env python3
"""
检查cumulative_main_net数据填充情况
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("检查cumulative_main_net数据填充情况")
print("=" * 80)

date = '20260428'
table_name = f"monitor_gp_sssj_{date}"

# 1. 检查有多少股票有非零的main_net_amount
print("\n【1】有主力净额的股票...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            SUM(main_net_amount) as total_main_net,
            COUNT(*) as record_count
        FROM {table_name}
        WHERE main_net_amount != 0
        GROUP BY stock_code
        ORDER BY total_main_net DESC
        LIMIT 10
    """))
    
    rows = result.fetchall()
    print(f"  有主力净额的股票数: {len(rows)}")
    for row in rows[:5]:
        print(f"    {row[0]}: 净额={row[1]:,.0f}, 记录数={row[2]}")

# 2. 检查cumulative_main_net的分布
print("\n【2】cumulative_main_net分布...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            CASE 
                WHEN cumulative_main_net = 0 THEN 'zero'
                WHEN cumulative_main_net IS NULL THEN 'null'
                ELSE 'non-zero'
            END as status,
            COUNT(*) as count
        FROM {table_name}
        GROUP BY status
    """))
    
    for row in result.fetchall():
        print(f"  {row[0]}: {row[1]}条")

# 3. 检查特定时间点的数据
print("\n【3】15:00:00时间点数据...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            main_net_amount,
            cumulative_main_net
        FROM {table_name}
        WHERE time = '15:00:00' AND main_net_amount != 0
        LIMIT 10
    """))
    
    for row in result.fetchall():
        print(f"  {row[0]}: main_net={row[1]:,.0f}, cumulative={row[2]}")

print("\n" + "=" * 80)
print("结论: cumulative_main_net字段数据未填充，需要运行填充脚本")
