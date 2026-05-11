# -*- coding: utf-8 -*-
import pymysql

conn = pymysql.connect(host='192.168.0.101', port=3306, user='root',
                       password='123456', database='gs', charset='utf8mb4',
                       connect_timeout=10, read_timeout=30)
cur = conn.cursor(pymysql.cursors.DictCursor)

out = []

queries = [
    ('S级(85+)', "overnight_score >= 85 ORDER BY overnight_score DESC"),
    ('A级(70-84)', "overnight_score BETWEEN 70 AND 84 ORDER BY overnight_score DESC"),
    ('B级(50-69)', "overnight_score BETWEEN 50 AND 69 ORDER BY overnight_score DESC"),
    ('利好样本', "notice_type='利好' AND risk_level='高' ORDER BY overnight_score DESC"),
    ('利空样本', "notice_type='利空' AND risk_level='高' ORDER BY overnight_score DESC"),
]

fields = ['stock_code', 'stock_name', 'notice_title', 'notice_type', 'risk_level',
          'notice_category', 'core_content', 'risk_score', 'type_score', 'overnight_score',
          'market_expectation', 'open_prediction', 'duration', 'overnight_strategy',
          'short_term_impact', 'medium_term_impact', 'key_points', 'judgment_basis']

for label, where in queries:
    cur.execute(f"""
    SELECT {', '.join(f'`{f}`' for f in fields)} 
    FROM analysis_notice_detail_2026 
    WHERE overnight_score > 0 AND {where}
    LIMIT 1
    """)
    row = cur.fetchone()
    out.append(f'\n=== {label} ===')
    if row:
        for k, v in row.items():
            val = str(v)[:200] if v else 'NULL'
            out.append(f'  {k}: {val}')
    else:
        out.append('  无数据')

cur.execute("""
SELECT 
  CASE 
    WHEN overnight_score >= 85 THEN 'S级'
    WHEN overnight_score >= 70 THEN 'A级'
    WHEN overnight_score >= 50 THEN 'B级'
    WHEN overnight_score >= 30 THEN 'C级'
    ELSE 'D级'
  END as grade,
  COUNT(*) as cnt
FROM analysis_notice_detail_2026 
WHERE overnight_score > 0
GROUP BY grade ORDER BY grade
""")
out.append('\n=== 各档位分布 ===')
for r in cur.fetchall():
    out.append(f"  {r['grade']}: {r['cnt']}条")

cur.close()
conn.close()

with open(r'F:\pyworkspace2026\gs2026\detail_samples.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('done')
