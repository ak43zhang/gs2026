#!/usr/bin/env python3
"""
快速为Top 30股票填充累计主力净额
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("快速填充Top 30股票累计主力净额")
print("=" * 80)

date = '20260428'
table_name = f"monitor_gp_sssj_{date}"

# 使用单个UPDATE语句为所有股票填充
print("\n【1】使用窗口函数批量填充...")

update_sql = f"""
    UPDATE {table_name} t1
    JOIN (
        SELECT 
            stock_code,
            time,
            SUM(main_net_amount) OVER (
                PARTITION BY stock_code
                ORDER BY time 
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) as calculated_cumulative
        FROM {table_name}
        WHERE main_net_amount != 0
    ) t2 ON t1.stock_code = t2.stock_code AND t1.time = t2.time
    SET t1.cumulative_main_net = t2.calculated_cumulative
    WHERE t1.main_net_amount != 0
"""

print("  执行批量更新...")
with engine.connect() as conn:
    result = conn.execute(text(update_sql))
    conn.commit()
    print(f"  更新完成")

# 验证结果
print("\n【2】验证结果...")
with engine.connect() as conn:
    # 统计更新数量
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as non_zero
        FROM {table_name}
    """))
    
    row = result.fetchone()
    print(f"  总记录: {row[0]:,}")
    print(f"  非零累计值: {row[1]:,}")
    
    # 显示Top 10
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            short_name,
            cumulative_main_net
        FROM {table_name}
        WHERE time = '15:00:00' 
        AND cumulative_main_net != 0
        ORDER BY ABS(cumulative_main_net) DESC
        LIMIT 10
    """))
    
    print("\n  Top 10 累计主力净额 (15:00:00):")
    for i, row in enumerate(result.fetchall(), 1):
        print(f"    {i}. {row[0]} {row[1]}: {row[2]:,.0f}")

print(f"\n{'='*80}")
print("填充完成")
