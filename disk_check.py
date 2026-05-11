# -*- coding: utf-8 -*-
import pymysql

conn = pymysql.connect(host='192.168.0.101', port=3306, user='root',
                       password='123456', database='gs', charset='utf8mb4',
                       connect_timeout=10, read_timeout=30)
cur = conn.cursor()

out = []

# 1. 查看binlog列表和大小
cur.execute("SHOW BINARY LOGS")
logs = cur.fetchall()
total_size = 0
out.append(f'=== Binary Logs ({len(logs)}个) ===')
out.append(f'{"文件名":30s} {"大小(MB)":>10s}')
for log in logs:
    size_mb = log[1] / 1024 / 1024
    total_size += log[1]
    out.append(f'  {log[0]:30s} {size_mb:10.1f} MB')
out.append(f'  {"总计":30s} {total_size/1024/1024/1024:10.2f} GB')
out.append('')

# 2. 当前binlog配置
cur.execute("SHOW VARIABLES LIKE 'binlog_expire_logs_seconds'")
r = cur.fetchone()
out.append(f'binlog_expire_logs_seconds: {r[1] if r else "N/A"}')

cur.execute("SHOW VARIABLES LIKE 'expire_logs_days'")
r = cur.fetchone()
out.append(f'expire_logs_days: {r[1] if r else "N/A"}')

cur.execute("SHOW VARIABLES LIKE 'max_binlog_size'")
r = cur.fetchone()
out.append(f'max_binlog_size: {r[1] if r else "N/A"}')

cur.execute("SHOW VARIABLES LIKE 'log_bin'")
r = cur.fetchone()
out.append(f'log_bin: {r[1] if r else "N/A"}')

cur.execute("SHOW VARIABLES LIKE 'binlog_format'")
r = cur.fetchone()
out.append(f'binlog_format: {r[1] if r else "N/A"}')
out.append('')

# 3. 磁盘使用 - 数据库大小
cur.execute("""
SELECT table_schema AS db,
       ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) AS size_gb
FROM information_schema.TABLES
GROUP BY table_schema
ORDER BY size_gb DESC
LIMIT 10
""")
out.append('=== 数据库大小 TOP10 ===')
for r in cur.fetchall():
    out.append(f'  {r[0]:30s} {r[1]:8.2f} GB')
out.append('')

# 4. gs库中大表
cur.execute("""
SELECT table_name,
       ROUND((data_length + index_length) / 1024 / 1024, 1) AS size_mb,
       table_rows
FROM information_schema.TABLES
WHERE table_schema = 'gs'
ORDER BY (data_length + index_length) DESC
LIMIT 15
""")
out.append('=== gs库大表 TOP15 ===')
out.append(f'  {"表名":40s} {"大小(MB)":>10s} {"行数":>12s}')
for r in cur.fetchall():
    out.append(f'  {r[0]:40s} {r[1]:10.1f} {r[2]:12d}')

cur.close()
conn.close()

with open(r'F:\pyworkspace2026\gs2026\disk_check.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('done')
