#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

# 设置UTF-8编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import pymysql
import redis
import json
import pandas as pd
import time

worker_id = int(sys.argv[1])
total_workers = int(sys.argv[2])

print(f"Worker {worker_id}/{total_workers} started", flush=True)

# MySQL连接
mysql_conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)
mysql_cursor = mysql_conn.cursor()

# Redis连接
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

date_str = '20260429'
table_name = f"monitor_gp_sssj_{date_str}"

# 获取股票列表
mysql_cursor.execute(f"""
    SELECT DISTINCT stock_code 
    FROM {table_name}
    WHERE amount > 0
    AND MOD(CRC32(stock_code), {total_workers}) = {worker_id - 1}
""")

stocks = [r[0] for r in mysql_cursor.fetchall()]
print(f"Worker {worker_id}: {len(stocks)} stocks", flush=True)

total_mysql = 0
total_redis = 0
start = time.time()

for i, code in enumerate(stocks, 1):
    try:
        # 查询
        mysql_cursor.execute(f"""
            SELECT time, amount FROM {table_name}
            WHERE stock_code = %s ORDER BY time
        """, (code,))
        
        rows = mysql_cursor.fetchall()
        if len(rows) < 2:
            continue
        
        # 计算
        prev_amount = None
        cumulative = 0
        mysql_updates = []
        redis_updates = {}
        
        for time_str, amount in rows:
            try:
                amount = float(amount) if amount else 0
            except:
                amount = 0
            
            main_net = 0 if prev_amount is None else (amount - prev_amount) * 0.3
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
            data = redis_client.get(redis_key)
            if data:
                df = pd.DataFrame(json.loads(data))
                mask = df['stock_code'] == code
                if mask.any():
                    df.loc[mask, 'main_net_amount'] = main_net
                    df.loc[mask, 'cumulative_main_net'] = cum
                    redis_client.set(redis_key, df.to_json(orient='records'))
                    total_redis += 1
        
        # 进度报告
        if i % 100 == 0:
            elapsed = time.time() - start
            print(f"Worker {worker_id}: {i}/{len(stocks)} stocks, MySQL: {total_mysql}, Redis: {total_redis}, Time: {elapsed/60:.1f}min", flush=True)
            
    except Exception as e:
        print(f"Worker {worker_id}: Error on {code}: {e}", flush=True)

mysql_conn.close()
redis_client.close()

elapsed = time.time() - start
print(f"Worker {worker_id} completed! MySQL: {total_mysql}, Redis: {total_redis}, Time: {elapsed/60:.1f}min", flush=True)
