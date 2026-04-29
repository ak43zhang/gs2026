#!/usr/bin/env python3
"""
调试版工作进程
"""
import pymysql
import redis
import json
import pandas as pd
import sys
import time
import traceback

worker_id = int(sys.argv[1])
total_workers = int(sys.argv[2])

print(f"[进程{worker_id}/{total_workers}] 启动...")

try:
    # MySQL连接
    print("  连接MySQL...")
    mysql_conn = pymysql.connect(
        host='192.168.0.101', port=3306, user='root', password='123456',
        database='gs', charset='utf8mb4'
    )
    mysql_cursor = mysql_conn.cursor()
    print("  MySQL连接成功")

    # Redis连接
    print("  连接Redis...")
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    redis_client.ping()
    print("  Redis连接成功")

    date_str = '20260429'
    table_name = f"monitor_gp_sssj_{date_str}"

    # 获取该进程负责的股票
    print(f"  查询股票列表...")
    mysql_cursor.execute(f"""
        SELECT DISTINCT stock_code 
        FROM {table_name}
        WHERE amount > 0
        AND MOD(CRC32(stock_code), {total_workers}) = {worker_id - 1}
    """)

    stocks = [r[0] for r in mysql_cursor.fetchall()]
    print(f"  负责 {len(stocks)} 只股票")

    if len(stocks) == 0:
        print("  没有需要处理的股票，退出")
        sys.exit(0)

    # 只处理前5只测试
    test_stocks = stocks[:5]
    print(f"  测试模式：只处理前5只")

    for i, code in enumerate(test_stocks, 1):
        print(f"\n  [{i}/{len(test_stocks)}] 处理 {code}...")
        
        # 查询数据
        mysql_cursor.execute(f"""
            SELECT time, amount
            FROM {table_name}
            WHERE stock_code = %s
            ORDER BY time
        """, (code,))
        
        rows = mysql_cursor.fetchall()
        print(f"    数据条数: {len(rows)}")
        
        if len(rows) < 2:
            print(f"    跳过（数据不足）")
            continue
        
        # 计算
        prev_amount = None
        cumulative = 0
        mysql_updates = []
        
        for time_str, amount in rows[:3]:  # 只计算前3条
            try:
                amount = float(amount) if amount else 0
            except:
                amount = 0
            
            if prev_amount is None:
                main_net = 0
                print(f"    {time_str}: amount={amount:,.0f}, main_net=0 (首次)")
            else:
                main_net = (amount - prev_amount) * 0.3
                print(f"    {time_str}: amount={amount:,.0f}, main_net={main_net:,.0f}")
            
            cumulative += main_net
            prev_amount = amount
            mysql_updates.append((main_net, cumulative, code, time_str))
        
        print(f"    累计: {cumulative:,.0f}")
        
        # 更新MySQL
        print(f"    更新MySQL...")
        mysql_cursor.executemany(f"""
            UPDATE {table_name}
            SET main_net_amount = %s,
                cumulative_main_net = %s
            WHERE stock_code = %s AND time = %s
        """, mysql_updates)
        
        mysql_conn.commit()
        print(f"    MySQL更新: {len(mysql_updates)} 条")

    print("\n测试完成!")
    mysql_conn.close()
    redis_client.close()

except Exception as e:
    print(f"\n错误: {e}")
    traceback.print_exc()
    sys.exit(1)
