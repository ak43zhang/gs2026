#!/usr/bin/env python3
"""
工作进程 - 处理1000只股票
用法: python fill_worker.py <worker_id> <total_workers>
"""
import pymysql
import sys
import time

worker_id = int(sys.argv[1])
total_workers = int(sys.argv[2])

print(f"[进程{worker_id}/{total_workers}] 启动...")

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)

cursor = conn.cursor()

# 获取该进程负责的股票 (按stock_code哈希分配)
cursor.execute(f"""
    SELECT DISTINCT stock_code 
    FROM monitor_gp_sssj_20260429 
    WHERE amount > 0
    AND MOD(CRC32(stock_code), {total_workers}) = {worker_id - 1}
""")

stocks = [r[0] for r in cursor.fetchall()]
print(f"[进程{worker_id}] 负责 {len(stocks)} 只股票")

total_updated = 0
start = time.time()

for i, code in enumerate(stocks, 1):
    try:
        # 1. 查询该股票所有数据
        cursor.execute("""
            SELECT time, amount 
            FROM monitor_gp_sssj_20260429 
            WHERE stock_code = %s 
            ORDER BY time
        """, (code,))
        
        rows = cursor.fetchall()
        if len(rows) < 2:
            continue
        
        # 2. 内存计算
        prev_amount = None
        cumulative = 0
        updates = []
        
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
            updates.append((main_net, cumulative, code, time_str))
        
        # 3. 批量更新
        cursor.executemany("""
            UPDATE monitor_gp_sssj_20260429 
            SET main_net_amount = %s,
                cumulative_main_net = %s
            WHERE stock_code = %s AND time = %s
        """, updates)
        
        conn.commit()
        total_updated += len(updates)
        
        # 每100只报告进度
        if i % 100 == 0:
            elapsed = time.time() - start
            speed = i / elapsed if elapsed > 0 else 0
            remaining = (len(stocks) - i) / speed if speed > 0 else 0
            print(f"[进程{worker_id}] {i}/{len(stocks)} 只，"
                  f"已更新 {total_updated} 条，"
                  f"用时 {elapsed/60:.1f}分钟，"
                  f"预计剩余 {remaining/60:.1f}分钟")
                  
    except Exception as e:
        print(f"[进程{worker_id}] {code} 失败: {e}")

conn.close()

elapsed = time.time() - start
print(f"[进程{worker_id}] 完成! 更新 {total_updated} 条，用时 {elapsed/60:.1f}分钟")
