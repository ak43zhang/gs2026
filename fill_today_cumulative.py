#!/usr/bin/env python3
"""
填充今天(2026-04-29)的累计主力净额数据
"""
from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("填充2026-04-29累计主力净额数据")
print("=" * 80)

date = '20260429'
table_name = f"monitor_gp_sssj_{date}"

# 1. 检查当前状态
print("\n【1】检查当前状态...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
    """))
    
    row = result.fetchone()
    print(f"  总记录: {row[0]:,}")
    print(f"  非零main_net_amount: {row[1]:,}")
    print(f"  非零cumulative_main_net: {row[2]:,}")

# 2. 获取有主力净额的股票列表
print("\n【2】获取有主力净额的股票...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT DISTINCT stock_code
        FROM {table_name}
        WHERE main_net_amount != 0
    """))
    
    stock_codes = [row[0] for row in result.fetchall()]
    print(f"  有主力净额的股票: {len(stock_codes)}只")

if len(stock_codes) == 0:
    print("  没有需要填充的数据")
    exit(0)

# 3. 为每只股票填充累计值
print("\n【3】填充累计主力净额...")
total_updated = 0

for idx, stock_code in enumerate(stock_codes, 1):
    if idx % 50 == 0:
        print(f"  处理: {idx}/{len(stock_codes)}...")
    
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
            conn.execute(text(update_sql))
            conn.commit()
            
            # 统计
            count_result = conn.execute(text(f"""
                SELECT COUNT(*) 
                FROM {table_name} 
                WHERE stock_code = '{stock_code}'
                AND cumulative_main_net != 0
            """)).fetchone()
            
            total_updated += count_result[0]
            
    except Exception as e:
        print(f"  {stock_code} 失败: {e}")

# 4. 验证结果
print(f"\n【4】验证结果...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
    """))
    
    row = result.fetchone()
    print(f"  总记录: {row[0]:,}")
    print(f"  非零cumulative_main_net: {row[1]:,}")
    
    # 显示Top 10
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            short_name,
            MAX(time) as latest_time,
            cumulative_main_net
        FROM {table_name}
        WHERE cumulative_main_net != 0
        GROUP BY stock_code, short_name
        ORDER BY ABS(cumulative_main_net) DESC
        LIMIT 10
    """))
    
    print("\n  Top 10 累计主力净额:")
    for i, row in enumerate(result.fetchall(), 1):
        print(f"    {i}. {row[0]} {row[1]}: {row[3]:,.0f} (时间: {row[2]})")

print(f"\n{'='*80}")
print(f"填充完成: 共更新 {total_updated} 条记录")
