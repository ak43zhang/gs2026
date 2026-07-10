#!/usr/bin/env python3
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pymysql
import time

start = time.time()
conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root',
    password='123456', database='gs', charset='utf8'
)

try:
    with conn.cursor() as cursor:
        print("查询tick时间点...")
        cursor.execute("""
            SELECT DISTINCT time FROM monitor_zq_sssj_20260709
            WHERE time BETWEEN '093000' AND '150000'
            ORDER BY time
            LIMIT 10
        """)
        rows = cursor.fetchall()
        print(f"前10个tick: {[r[0] for r in rows]}")
        print(f"耗时: {time.time() - start:.2f}s")
finally:
    conn.close()
