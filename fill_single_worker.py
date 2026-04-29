#!/usr/bin/env python3
"""
单进程工作器 - 处理一部分股票
用法: python fill_single_worker.py <worker_id> <total_workers>
"""
import sys
import pymysql
import redis
import json
import time

# 参数
worker_id = int(sys.argv[1])
total_workers = int(sys.argv[2])

# 日志文件
log_file = open(f'worker_{worker_id}_of_{total_workers}.log', 'w', encoding='utf-8')

def log(msg):
    timestamp = time.strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    log_file.write(line + '\n')
    log_file.flush()

log(f"Worker {worker_id}/{total_workers} started")

# 连接MySQL
log("Connecting to MySQL...")
mysql_conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)
mysql_cursor = mysql_conn.cursor()
log("MySQL connected")

# 连接Redis
log("Connecting to Redis...")
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
redis_client.ping()
log("Redis connected")

date_str = '20260429'
table_name = f"monitor_gp_sssj_{date_str}"

# 获取该worker负责的股票
log("Fetching stock list...")
mysql_cursor.execute(f"""
    SELECT DISTINCT stock_code 
    FROM {table_name}
    WHERE amount > 0
    AND MOD(CRC32(stock_code), {total_workers}) = {worker_id - 1}
""")

stocks = [r[0] for r in mysql_cursor.fetchall()]
log(f"Total stocks: {len(stocks)}")

total_mysql = 0
total_redis = 0
start_time = time.time()

for i, code in enumerate(stocks, 1):
    try:
        # 查询该股票数据
        mysql_cursor.execute(f"""
            SELECT time, amount FROM {table_name}
            WHERE stock_code = %s ORDER BY time
        """, (code,))
        
        rows = mysql_cursor.fetchall()
        if len(rows) < 2:
            continue
        
        # 计算主力净额
        prev_amount = None
        cumulative = 0
        mysql_updates = []
        redis_updates = {}
        
        for time_str, amount in rows:
            try:
                amount = float(amount) if amount else 0
            except:
                amount = 0
            
            if prev_amount is None:
                main_net = 0
            else:
                main_net = (amount - prev_amount) * 0.3
            
            cumulative += main_net
            prev_amount = amount
            
            mysql_updates.append((main_net, cumulative, code, time_str))
            redis_updates[time_str] = (main_net, cumulative)
        
        # 更新MySQL
        mysql_cursor.executemany(f"""
            UPDATE {table_name}
            SET main_net_amount = %s, cumulative_main_net = %s
            WHERE stock_code = %s AND time = %s
        """, mysql_updates)
        mysql_conn.commit()
        total_mysql += len(mysql_updates)
        
        # 更新Redis
        for time_str, (main_net, cum) in redis_updates.items():
            redis_key = f"{table_name}:{time_str}"
            try:
                data = redis_client.get(redis_key)
                if data:
                    df = json.loads(data)
                    for row in df:
                        if row.get('stock_code') == code:
                            row['main_net_amount'] = main_net
                            row['cumulative_main_net'] = cum
                    redis_client.set(redis_key, json.dumps(df))
                    total_redis += 1
            except:
                pass
        
        # 每50只股票报告进度
        if i % 50 == 0:
            elapsed = time.time() - start_time
            speed = i / elapsed if elapsed > 0 else 0
            remaining = (len(stocks) - i) / speed if speed > 0 else 0
            log(f"Progress: {i}/{len(stocks)} stocks, MySQL: {total_mysql}, Redis: {total_redis}, Elapsed: {elapsed/60:.1f}min, Remaining: {remaining/60:.1f}min")
            
    except Exception as e:
        log(f"Error on {code}: {str(e)}")

# 完成
elapsed = time.time() - start_time
log(f"Completed! MySQL: {total_mysql}, Redis: {total_redis}, Time: {elapsed/60:.1f}min")

mysql_conn.close()
redis_client.close()
log_file.close()
