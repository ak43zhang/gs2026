#!/usr/bin/env python3
"""检查数据量"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pymysql

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root',
    password='123456', database='gs', charset='utf8'
)

try:
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM monitor_zq_sssj_20260709 WHERE time BETWEEN '093000' AND '150000'")
        count = cursor.fetchone()[0]
        print(f"7月9日数据量: {count} 条")
        
        cursor.execute("SELECT COUNT(DISTINCT time) FROM monitor_zq_sssj_20260709 WHERE time BETWEEN '093000' AND '150000'")
        ticks = cursor.fetchone()[0]
        print(f"tick时间点数: {ticks}")
finally:
    conn.close()
