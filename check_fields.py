# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='192.168.0.101', port=3306, user='root', password='123456', database='gs', charset='utf8mb4')
cur = conn.cursor()
cur.execute('DESCRIBE analysis_notice_detail_2026')
for r in cur.fetchall():
    n = r[2] if r[2] else ''
    k = r[3] if r[3] else ''
    print(f'{r[0]:30s} {r[1]:30s} {n:5s} {k}')
cur.execute('SELECT * FROM analysis_notice_detail_2026 WHERE risk_level="高" AND notice_type="利好" LIMIT 1')
row = cur.fetchone()
cols = [d[0] for d in cur.description]
if row:
    print('\n--- SAMPLE: High+Bullish ---')
    for c, v in zip(cols, row):
        val = str(v)[:120] if v else 'NULL'
        print(f'{c:30s} = {val}')
cur.close()
conn.close()
