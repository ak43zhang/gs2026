# -*- coding: utf-8 -*-
import pymysql

conn = pymysql.connect(host='192.168.0.101', port=3306, user='root',
                       password='123456', database='gs', charset='utf8mb4',
                       connect_timeout=10, read_timeout=30)
cur = conn.cursor()

# 1. 缩短过期时间为3天
print('设置 binlog_expire_logs_seconds = 3天(259200s)...', flush=True)
cur.execute("SET GLOBAL binlog_expire_logs_seconds = 259200")
conn.commit()
print('done', flush=True)

# 2. 验证
cur.execute("SHOW VARIABLES LIKE 'binlog_expire_logs_seconds'")
print(f'当前设置: {cur.fetchone()[1]}', flush=True)

# 3. 立即清除3天前的binlog
print('PURGE BINARY LOGS BEFORE NOW() - INTERVAL 3 DAY...', flush=True)
cur.execute("PURGE BINARY LOGS BEFORE NOW() - INTERVAL 3 DAY")
conn.commit()
print('PURGE done', flush=True)

# 4. 查看剩余
cur.execute("SHOW BINARY LOGS")
remaining = cur.fetchall()
total = sum(r[1] for r in remaining)
print(f'剩余binlog: {len(remaining)}个, 共{total/1024/1024/1024:.2f} GB', flush=True)

cur.close()
conn.close()
print('all done', flush=True)
