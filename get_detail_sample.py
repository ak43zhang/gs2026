# -*- coding: utf-8 -*-
import pymysql, json

conn = pymysql.connect(host='192.168.0.101', port=3306, user='root',
                       password='123456', database='gs', charset='utf8mb4',
                       connect_timeout=10, read_timeout=30)
cur = conn.cursor(pymysql.cursors.DictCursor)

# 获取示例数据
cur.execute("""
SELECT * FROM analysis_notice_detail_2026 
WHERE content_hash = '7b24748b1979ce72a071b198ad52fd8f'
""")
row = cur.fetchone()

if not row:
    # 尝试用notice_id
    cur.execute("""
    SELECT * FROM analysis_notice_detail_2026 
    WHERE notice_id = '7b24748b1979ce72a071b198ad52fd8f'
    LIMIT 1
    """)
    row = cur.fetchone()

out = []
if row:
    out.append('=== 示例数据 ===')
    for k, v in row.items():
        val = str(v)[:200] if v else 'NULL'
        out.append(f'{k}: {val}')
else:
    out.append('未找到该记录，列出最新一条有分析结果的')
    cur.execute("""
    SELECT * FROM analysis_notice_detail_2026 
    WHERE analysis IS NOT NULL AND overnight_score > 50
    ORDER BY notice_date DESC LIMIT 1
    """)
    row = cur.fetchone()
    if row:
        for k, v in row.items():
            val = str(v)[:300] if v else 'NULL'
            out.append(f'{k}: {val}')

# 表结构
out.append('\n=== 表结构 ===')
cur.execute("SHOW COLUMNS FROM analysis_notice_detail_2026")
for col in cur.fetchall():
    out.append(f"  {col['Field']:30s} {col['Type']:20s} {col['Null']:5s} {col['Default'] or ''}")

cur.close()
conn.close()

with open(r'F:\pyworkspace2026\gs2026\detail_sample.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('done')
