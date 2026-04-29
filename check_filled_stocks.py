#!/usr/bin/env python3
"""
检查已填充的股票列表
"""
import pymysql

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)
cursor = conn.cursor()

print("=" * 60)
print("已填充主力净额的股票列表")
print("=" * 60)

# 获取已填充的股票
cursor.execute("""
    SELECT 
        stock_code,
        short_name,
        COUNT(*) as total_records,
        MAX(cumulative_main_net) as max_cumulative
    FROM monitor_gp_sssj_20260429
    WHERE main_net_amount != 0
    GROUP BY stock_code, short_name
    ORDER BY ABS(MAX(cumulative_main_net)) DESC
    LIMIT 30
""")

stocks = cursor.fetchall()

print(f"\n已填充股票数量: {len(stocks)} 只\n")

if len(stocks) > 0:
    print(f"{'排名':<4} {'股票代码':<10} {'股票名称':<10} {'记录数':<8} {'累计主力净额':<15}")
    print("-" * 60)
    
    for i, (code, name, count, cum) in enumerate(stocks, 1):
        cum_str = f"{cum:,.0f}" if cum else "0"
        print(f"{i:<4} {code:<10} {name:<10} {count:<8} {cum_str:<15}")

# 统计
cursor.execute("""
    SELECT 
        COUNT(DISTINCT stock_code) as total_stocks,
        SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as filled_records,
        COUNT(*) as total_records
    FROM monitor_gp_sssj_20260429
""")

row = cursor.fetchone()
print(f"\n{'='*60}")
print(f"总股票数: {row[0]} 只")
print(f"已填充记录: {row[1]:,} / {row[2]:,} ({row[1]/row[2]*100:.2f}%)")
print(f"{'='*60}")

conn.close()
