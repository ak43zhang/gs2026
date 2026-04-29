#!/usr/bin/env python3
"""
只填充股票上攻排行中的股票（约60只）
快速满足展示需求
"""
import pymysql
import time

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)

print("=" * 60)
print("填充股票上攻排行股票的主力净额")
print("=" * 60)

start = time.time()
cursor = conn.cursor()

# 获取上攻排行中的股票（从top30表）
cursor.execute("""
    SELECT DISTINCT stock_code 
    FROM monitor_gp_top30_20260429 
    LIMIT 100
""")
top_stocks = [r[0] for r in cursor.fetchall()]
print(f"\n上攻排行股票: {len(top_stocks)}只")

if len(top_stocks) == 0:
    # 如果没有top30数据，从实时数据中获取有成交额的股票
    cursor.execute("""
        SELECT DISTINCT stock_code 
        FROM monitor_gp_sssj_20260429 
        WHERE amount > 1000000 
        LIMIT 100
    """)
    top_stocks = [r[0] for r in cursor.fetchall()]
    print(f"实时数据股票: {len(top_stocks)}只")

total_updated = 0

for i, code in enumerate(top_stocks, 1):
    try:
        # 获取该股票的所有数据
        cursor.execute(f"""
            SELECT time, amount 
            FROM monitor_gp_sssj_20260429 
            WHERE stock_code = '{code}' 
            ORDER BY time
        """)
        rows = cursor.fetchall()
        
        if len(rows) < 2:
            continue
        
        # 计算
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
        
        # 批量更新
        for main_net, cumulative, code, time_str in updates:
            cursor.execute("""
                UPDATE monitor_gp_sssj_20260429 
                SET main_net_amount = %s,
                    cumulative_main_net = %s
                WHERE stock_code = %s AND time = %s
            """, (main_net, cumulative, code, time_str))
        
        conn.commit()
        total_updated += len(updates)
        
        if i % 10 == 0:
            elapsed = time.time() - start
            print(f"  进度: {i}/{len(top_stocks)} 只，已更新 {total_updated} 条，用时 {elapsed:.1f}秒")
            
    except Exception as e:
        print(f"  {code} 失败: {e}")

# 验证
cursor.execute("""
    SELECT 
        COUNT(*),
        SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END)
    FROM monitor_gp_sssj_20260429
""")
row = cursor.fetchone()

conn.close()

elapsed = time.time() - start
print(f"\n{'='*60}")
print(f"完成!")
print(f"  更新: {total_updated} 条")
print(f"  用时: {elapsed:.1f} 秒")
print(f"  当前总填充: {row[1]:,} 条 ({row[1]/row[0]*100:.2f}%)")
