#!/usr/bin/env python3
import pymysql

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root',
    password='123456', database='gs', charset='utf8'
)

try:
    with conn.cursor() as cursor:
        cursor.execute("DESCRIBE quant_screen_hits")
        print("quant_screen_hits 表结构:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")
finally:
    conn.close()
