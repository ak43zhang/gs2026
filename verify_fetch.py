# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='192.168.0.101', port=3306, user='root',
                       password='123456', database='gs', charset='utf8mb4',
                       connect_timeout=10, read_timeout=10)
cur = conn.cursor()

# 统计
cur.execute("SELECT content_status, COUNT(*) FROM jhsaggg2026 WHERE `公告日期`='2026-04-30' GROUP BY content_status")
out = ['=== 2026-04-30 抓取状态统计 ===']
for r in cur.fetchall():
    label = {0: '未抓取', 1: '有内容', 2: '仅PDF', 3: '失败'}.get(r[0], f'未知({r[0]})')
    out.append(f'  {label}: {r[1]}条')

# 看几条有内容的样本
cur.execute("SELECT `公告标题`, LEFT(`公告原文`, 100), content_status FROM jhsaggg2026 WHERE `公告日期`='2026-04-30' AND content_status=1 LIMIT 3")
out.append('\n=== 有内容样本 ===')
for r in cur.fetchall():
    out.append(f'  标题: {r[0][:60]}')
    out.append(f'  原文前100字: {r[1]}')
    out.append('')

# 看PDF样本
cur.execute("SELECT `公告标题`, `网址` FROM jhsaggg2026 WHERE `公告日期`='2026-04-30' AND content_status=2 LIMIT 3")
out.append('=== 仅PDF样本 ===')
for r in cur.fetchall():
    out.append(f'  标题: {r[0][:60]}')
    out.append(f'  网址: {r[1][:80]}')

cur.close()
conn.close()

with open(r'F:\pyworkspace2026\gs2026\verify_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('done')
