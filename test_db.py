import pymysql
import os

# 连接数据库
conn = pymysql.connect(
    host='localhost',
    user='root',
    password='123456',
    database='gs2026',
    charset='utf8mb4'
)

try:
    with conn.cursor() as cur:
        # 查询002859在2026-05-22的sssj数据
        cur.execute("SELECT * FROM monitor_gp_sssj_20260522 WHERE stock_code='002859' ORDER BY time DESC LIMIT 5")
        rows = cur.fetchall()
        print("Stock 002859 sssj data (last 5):")
        for row in rows:
            print(row)
        
        # 查询买点候选数据
        cur.execute("SELECT time, stock_code, stock_name, stock_price, stock_change_pct FROM buy_point_candidates WHERE date='2026-05-22' AND stock_code='002859' ORDER BY time LIMIT 3")
        rows = cur.fetchall()
        print("\nBuy point candidates for 002859:")
        for row in rows:
            print(f"  Time: {row[0]}, Price: {row[3]}, Change: {row[4]}")
            
finally:
    conn.close()
