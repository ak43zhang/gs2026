#!/usr/bin/env python3
"""
为上攻排行Top 30股票填充累计主力净额
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("为上攻排行股票填充累计主力净额")
print("=" * 80)

date = '20260428'
date_str = '2026-04-28'

# 1. 获取上攻排行Top 30股票
print("\n【1】获取上攻排行Top 30股票...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT code, name, count
        FROM rank_stock
        WHERE date = '{date}'
        ORDER BY count DESC
        LIMIT 30
    """))
    
    top30_stocks = [(row[0], row[1], row[2]) for row in result.fetchall()]
    
print(f"  Top 30股票数: {len(top30_stocks)}")
for i, (code, name, count) in enumerate(top30_stocks[:10], 1):
    print(f"    {i}. {code} {name}: {count}次")

# 2. 为每只股票填充累计主力净额
print("\n【2】填充累计主力净额...")
table_name = f"monitor_gp_sssj_{date}"
stock_codes = [code for code, _, _ in top30_stocks]

total_updated = 0
for idx, stock_code in enumerate(stock_codes, 1):
    print(f"  处理 {idx}/30: {stock_code}...", end=' ')
    
    try:
        # 使用窗口函数计算累计值
        update_sql = f"""
            UPDATE {table_name} t1
            JOIN (
                SELECT 
                    time,
                    SUM(main_net_amount) OVER (
                        ORDER BY time 
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) as calculated_cumulative
                FROM {table_name}
                WHERE stock_code = '{stock_code}'
            ) t2 ON t1.time = t2.time
            SET t1.cumulative_main_net = t2.calculated_cumulative
            WHERE t1.stock_code = '{stock_code}'
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(update_sql))
            conn.commit()
            
            # 统计更新数量
            count_result = conn.execute(text(f"""
                SELECT COUNT(*) 
                FROM {table_name} 
                WHERE stock_code = '{stock_code}'
                AND cumulative_main_net != 0
            """)).fetchone()
            
            updated = count_result[0]
            total_updated += updated
            print(f"更新 {updated} 条")
            
    except Exception as e:
        print(f"失败: {e}")

print(f"\n【3】验证结果...")
with engine.connect() as conn:
    # 检查15:00:00时间点的累计值
    codes_str = ','.join([f"'{c}'" for c in stock_codes])
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            main_net_amount,
            cumulative_main_net
        FROM {table_name}
        WHERE time = '15:00:00' 
        AND stock_code IN ({codes_str})
        AND cumulative_main_net != 0
        ORDER BY cumulative_main_net DESC
        LIMIT 10
    """))
    
    rows = result.fetchall()
    print(f"  15:00:00有累计值的股票: {len(rows)}只")
    for row in rows[:5]:
        print(f"    {row[0]}: main_net={row[1]:,.0f}, cumulative={row[2]:,.0f}")

print(f"\n{'='*80}")
print(f"填充完成: 共更新 {total_updated} 条记录")
