#!/usr/bin/env python3
"""测试回填"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pymysql

# 直接查询方案
conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', 
    password='123456', database='gs', charset='utf8'
)

try:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct, 
                   max_hold_time, price_offset, offset_mode
            FROM quant_screen_schemes 
            WHERE is_active = 1 AND use_realtime = 1
        """)
        rows = cursor.fetchall()
        print(f"找到 {len(rows)} 个在用方案:")
        for row in rows:
            print(f"  - {row[0]}")
finally:
    conn.close()

print("\n测试完成")
