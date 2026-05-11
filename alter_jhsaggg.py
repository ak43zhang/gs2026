# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='192.168.0.101', port=3306, user='root',
                       password='123456', database='gs', charset='utf8mb4',
                       connect_timeout=30, read_timeout=600)
cur = conn.cursor()

# 检查字段是否已存在
cur.execute("SHOW COLUMNS FROM jhsaggg2026 LIKE '公告原文'")
if cur.fetchone():
    print('公告原文 already exists')
else:
    print('Adding 公告原文 + content_status...', flush=True)
    cur.execute(
        "ALTER TABLE jhsaggg2026 "
        "ADD COLUMN `公告原文` LONGTEXT DEFAULT NULL COMMENT '东方财富API获取的公告全文', "
        "ADD COLUMN `content_status` TINYINT DEFAULT 0 COMMENT '0=未抓取,1=有内容,2=仅PDF,3=失败'"
    )
    conn.commit()
    print('ALTER TABLE done!', flush=True)

cur.execute("SHOW COLUMNS FROM jhsaggg2026 WHERE Field IN ('公告原文','content_status')")
for r in cur.fetchall():
    print(f'  {r[0]} | {r[1]}', flush=True)
cur.close()
conn.close()
print('all done')
