#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pymysql

# 直接连接
conn = pymysql.connect(
    host='192.168.0.101',
    port=3306,
    user='root',
    password='123456',
    database='gs',
    charset='utf8mb4'
)

try:
    with conn.cursor() as cursor:
        cursor.execute("SELECT stock_code, stock_name FROM analysis_ztb_detail_2026 WHERE trade_date = '2026-04-13' LIMIT 3")
        results = cursor.fetchall()
        for row in results:
            print(f"{row[0]}: {row[1]}")
finally:
    conn.close()
