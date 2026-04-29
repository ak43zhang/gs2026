#!/usr/bin/env python3
"""
只填充上攻排行中的股票（约60只）
同时更新MySQL和Redis
"""
import pymysql
import redis
import json
import time

print("=" * 60)
print("填充上攻排行股票主力净额")
print("=" * 60)

# 连接
mysql_conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)
mysql_cursor = mysql_conn.cursor()

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

date_str = '20260429'
table_name = f"monitor_gp_sssj_{date_str}"

# 获取上攻排行股票
print("\n获取上攻排行股票...")
mysql_cursor.execute(f"""
    SELECT DISTINCT code 
    FROM monitor_gp_top30_{date_str}
""")

top_stocks = [r[0] for r in mysql_cursor.fetchall()]
print(f"上攻排行股票: {len(top_stocks)}只")

if len(top_stocks) == 0:
    print("Top30表为空，从实时数据获取...")
    mysql_cursor.execute(f"""
        SELECT DISTINCT stock_code 
        FROM {table_name}
        WHERE amount > 10000000
        LIMIT 60
    """)
    top_stocks = [r[0] for r in mysql_cursor.fetchall()]
    print(f"实时数据股票: {len(top_stocks)}只")

total_mysql = 0
total_redis = 0
start_time = time.time()

for i, code in enumerate(top_stocks, 1):
    try:
        # 查询数据
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
        
        for time_str, amount in rows:
            try:
                amount = float(amount) if amount else 0
            except:
                amount = 0
            
            main_net = 0 if prev_amount is None else (amount - prev_amount) * 0.3
            cumulative += main_net
            prev_amount = amount
            mysql_updates.append((main_net, cumulative, code, time_str))
        
        # 更新MySQL
        mysql_cursor.executemany(f"""
            UPDATE {table_name}
            SET main_net_amount = %s, cumulative_main_net = %s
            WHERE stock_code = %s AND time = %s
        """, mysql_updates)
        mysql_conn.commit()
        total_mysql += len(mysql_updates)
        
        # 更新Redis
        for row in mysql_updates:
            main_net, cum, code, time_str = row
            redis_key = f"{table_name}:{time_str}"
            try:
                data = redis_client.get(redis_key)
                if data:
                    df = json.loads(data)
                    for r in df:
                        if r.get('stock_code') == code:
                            r['main_net_amount'] = main_net
                            r['cumulative_main_net'] = cum
                    redis_client.set(redis_key, json.dumps(df))
                    total_redis += 1
            except:
                pass
        
        # 每10只报告
        if i % 10 == 0:
            elapsed = time.time() - start_time
            print(f"  {i}/{len(top_stocks)} 只，MySQL: {total_mysql}，Redis: {total_redis}，用时: {elapsed:.1f}秒")
            
    except Exception as e:
        print(f"  {code} 错误: {e}")

# 统计
elapsed = time.time() - start_time
print(f"\n{'='*60}")
print(f"完成!")
print(f"  股票: {len(top_stocks)}只")
print(f"  MySQL: {total_mysql}条")
print(f"  Redis: {total_redis}条")
print(f"  用时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")

mysql_conn.close()
redis_client.close()
