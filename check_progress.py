#!/usr/bin/env python3
"""
检查填充进度
"""
import pymysql

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)

cursor = conn.cursor()

print("=" * 60)
print("填充进度检查")
print("=" * 60)

cursor.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
        SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
    FROM monitor_gp_sssj_20260429
""")

row = cursor.fetchone()
total = row[0]
main = row[1]
cum = row[2]

print(f"\n总记录: {total:,}")
print(f"已填充 main_net_amount: {main:,} ({main/total*100:.2f}%)")
print(f"已填充 cumulative_main_net: {cum:,} ({cum/total*100:.2f}%)")

# 按小时统计
print("\n按小时统计:")
cursor.execute("""
    SELECT 
        SUBSTRING(time, 1, 2) as hour,
        COUNT(*) as total,
        SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero
    FROM monitor_gp_sssj_20260429
    GROUP BY SUBSTRING(time, 1, 2)
    ORDER BY hour
""")

for row in cursor.fetchall():
    hour = row[0]
    total_hour = row[1]
    main_hour = row[2]
    pct = main_hour/total_hour*100 if total_hour > 0 else 0
    print(f"  {hour}:00 - {main_hour:,}/{total_hour:,} ({pct:.1f}%)")

# Top 10
cursor.execute("""
    SELECT 
        stock_code,
        short_name,
        MAX(cumulative_main_net) as max_cum
    FROM monitor_gp_sssj_20260429
    WHERE cumulative_main_net != 0
    GROUP BY stock_code, short_name
    ORDER BY ABS(MAX(cumulative_main_net)) DESC
    LIMIT 10
""")

print("\nTop 10 累计主力净额:")
for i, row in enumerate(cursor.fetchall(), 1):
    print(f"  {i}. {row[0]} {row[1]}: {row[2]:,.0f}")

conn.close()

print("\n" + "=" * 60)
