#!/usr/bin/env python3
"""
工作进程v2 - 同时填充MySQL和Redis
用法: python fill_worker_v2.py <worker_id> <total_workers>
"""
import pymysql
import redis
import sys
import time
import pandas as pd
import zlib
import pickle

worker_id = int(sys.argv[1])
total_workers = int(sys.argv[2])

print(f"[进程{worker_id}/{total_workers}] 启动...")

# MySQL连接
mysql_conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)
mysql_cursor = mysql_conn.cursor()

# Redis连接
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)

date_str = '20260429'
table_name = f"monitor_gp_sssj_{date_str}"

# 获取该进程负责的股票
mysql_cursor.execute(f"""
    SELECT DISTINCT stock_code 
    FROM {table_name}
    WHERE amount > 0
    AND MOD(CRC32(stock_code), {total_workers}) = {worker_id - 1}
""")

stocks = [r[0] for r in mysql_cursor.fetchall()]
print(f"[进程{worker_id}] 负责 {len(stocks)} 只股票")

total_updated_mysql = 0
total_updated_redis = 0
start = time.time()

for i, code in enumerate(stocks, 1):
    try:
        # 1. 查询该股票所有数据（MySQL）
        mysql_cursor.execute(f"""
            SELECT time, amount, price, change_pct, short_name
            FROM {table_name}
            WHERE stock_code = %s 
            ORDER BY time
        """, (code,))
        
        rows = mysql_cursor.fetchall()
        if len(rows) < 2:
            continue
        
        # 2. 内存计算
        prev_amount = None
        cumulative = 0
        mysql_updates = []
        redis_updates = {}  # time -> data
        
        for row in rows:
            time_str = row[0]
            amount = float(row[1]) if row[1] else 0
            price = row[2]
            change_pct = row[3]
            short_name = row[4]
            
            if prev_amount is None:
                main_net = 0
            else:
                main_net = (amount - prev_amount) * 0.3
            
            cumulative += main_net
            prev_amount = amount
            
            # MySQL更新
            mysql_updates.append((main_net, cumulative, code, time_str))
            
            # Redis更新
            redis_updates[time_str] = {
                'main_net_amount': main_net,
                'cumulative_main_net': cumulative
            }
        
        # 3. 批量更新MySQL
        mysql_cursor.executemany(f"""
            UPDATE {table_name}
            SET main_net_amount = %s,
                cumulative_main_net = %s
            WHERE stock_code = %s AND time = %s
        """, mysql_updates)
        
        mysql_conn.commit()
        total_updated_mysql += len(mysql_updates)
        
        # 4. 批量更新Redis
        # 获取该股票的所有时间点的Redis数据
        for time_str, data in redis_updates.items():
            redis_key = f"{table_name}:{time_str}"
            
            # 获取现有数据
            existing_data = redis_client.get(redis_key)
            if existing_data:
                try:
                    df = pickle.loads(zlib.decompress(existing_data))
                except:
                    df = pickle.loads(existing_data)
                
                # 更新该股票的数据
                mask = df['stock_code'] == code
                if mask.any():
                    df.loc[mask, 'main_net_amount'] = data['main_net_amount']
                    df.loc[mask, 'cumulative_main_net'] = data['cumulative_main_net']
                    
                    # 压缩并保存
                    compressed = zlib.compress(pickle.dumps(df), level=6)
                    redis_client.set(redis_key, compressed)
                    total_updated_redis += 1
        
        # 每100只报告进度
        if i % 100 == 0:
            elapsed = time.time() - start
            speed = i / elapsed if elapsed > 0 else 0
            remaining = (len(stocks) - i) / speed if speed > 0 else 0
            print(f"[进程{worker_id}] {i}/{len(stocks)} 只，"
                  f"MySQL: {total_updated_mysql} 条，"
                  f"Redis: {total_updated_redis} 条，"
                  f"用时 {elapsed/60:.1f}分钟，"
                  f"预计剩余 {remaining/60:.1f}分钟")
                  
    except Exception as e:
        print(f"[进程{worker_id}] {code} 失败: {e}")
        import traceback
        traceback.print_exc()

mysql_conn.close()
redis_client.close()

elapsed = time.time() - start
print(f"[进程{worker_id}] 完成! MySQL: {total_updated_mysql} 条, Redis: {total_updated_redis} 条, 用时 {elapsed/60:.1f}分钟")
