#!/usr/bin/env python3
"""
为有主力净额数据的股票填充累计主力净额
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("为有主力净额数据的股票填充累计主力净额")
print("=" * 80)

date = '20260428'
table_name = f"monitor_gp_sssj_{date}"

# 1. 获取有主力净额数据的股票
print("\n【1】获取有主力净额数据的股票...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            short_name,
            SUM(ABS(main_net_amount)) as total_main_net,
            COUNT(*) as record_count
        FROM {table_name}
        WHERE main_net_amount != 0
        GROUP BY stock_code, short_name
        ORDER BY total_main_net DESC
        LIMIT 60
    """))
    
    top_stocks = [(row[0], row[1], row[2], row[3]) for row in result.fetchall()]
    
print(f"  有主力净额的股票数: {len(top_stocks)}")
for i, (code, name, total, count) in enumerate(top_stocks[:10], 1):
    print(f"    {i}. {code} {name}: 总净额={total:,.0f}, 记录数={count}")

if len(top_stocks) == 0:
    print("  没有主力净额数据！")
    sys.exit(1)

# 2. 为每只股票填充累计主力净额
print("\n【2】填充累计主力净额...")
stock_codes = [code for code, _, _, _ in top_stocks]

total_updated = 0
for idx, stock_code in enumerate(stock_codes, 1):
    print(f"  处理 {idx}/{len(stock_codes)}: {stock_code}...", end=' ')
    
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

# 3. 验证结果
print(f"\n【3】验证结果...")
with engine.connect() as conn:
    # 检查15:00:00时间点的累计值
    codes_str = ','.join([f"'{c}'" for c in stock_codes[:30]])
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            short_name,
            main_net_amount,
            cumulative_main_net
        FROM {table_name}
        WHERE time = '15:00:00' 
        AND stock_code IN ({codes_str})
        AND cumulative_main_net != 0
        ORDER BY ABS(cumulative_main_net) DESC
        LIMIT 10
    """))
    
    rows = result.fetchall()
    print(f"  15:00:00有累计值的股票: {len(rows)}只")
    for row in rows[:10]:
        print(f"    {row[0]} {row[1]}: main_net={row[2]:,.0f}, cumulative={row[3]:,.0f}")

print(f"\n{'='*80}")
print(f"填充完成: 共处理 {len(stock_codes)} 只股票，更新 {total_updated} 条记录")
