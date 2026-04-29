#!/usr/bin/env python3
"""
简化版填充 - 单线程，每只股票单独处理
"""
import pymysql
import time

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)

print("开始填充...")
start = time.time()

cursor = conn.cursor()

# 获取有数据的股票（限制100只测试）
cursor.execute("SELECT DISTINCT stock_code FROM monitor_gp_sssj_20260429 WHERE amount > 0 LIMIT 100")
stocks = [r[0] for r in cursor.fetchall()]
print(f"处理 {len(stocks)} 只股票")

total_updated = 0

for i, code in enumerate(stocks, 1):
    # 获取该股票的所有数据
    cursor.execute(f"""
        SELECT time, amount FROM monitor_gp_sssj_20260429 
        WHERE stock_code = '{code}' ORDER BY time
    """)
    rows = cursor.fetchall()
    
    if len(rows) < 2:
        continue
    
    # 计算
    prev_amount = None
    cumulative = 0
    
    for time_str, amount in rows:
        amount = float(amount) if amount else 0
        
        if prev_amount is None:
            main_net = 0
        else:
            main_net = (amount - prev_amount) * 0.3
        
        cumulative += main_net
        prev_amount = amount
        
        # 更新
        cursor.execute(f"""
            UPDATE monitor_gp_sssj_20260429 
            SET main_net_amount = {main_net:.2f},
                cumulative_main_net = {cumulative:.2f}
            WHERE stock_code = '{code}' AND time = '{time_str}'
        """)
    
    conn.commit()
    total_updated += len(rows)
    
    if i % 10 == 0:
        elapsed = time.time() - start
        print(f"  {i}/{len(stocks)} 只，已更新 {total_updated} 条，用时 {elapsed:.1f}秒")

conn.close()

elapsed = time.time() - start
print(f"\n完成: 更新 {total_updated} 条，用时 {elapsed:.1f}秒")
