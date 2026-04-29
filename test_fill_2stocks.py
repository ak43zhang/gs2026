#!/usr/bin/env python3
"""
测试2只股票，验证填充流程
"""
import pymysql
import time

print("=" * 60)
print("测试2只股票填充流程")
print("=" * 60)

conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)

cursor = conn.cursor()

# 选择2只有数据的股票
cursor.execute("""
    SELECT DISTINCT stock_code 
    FROM monitor_gp_sssj_20260429 
    WHERE amount > 0
    LIMIT 2
""")

test_stocks = [r[0] for r in cursor.fetchall()]
print(f"\n测试股票: {test_stocks}")

for code in test_stocks:
    print(f"\n{'='*60}")
    print(f"处理股票: {code}")
    print(f"{'='*60}")
    
    # 1. 查询该股票数据
    cursor.execute(f"""
        SELECT time, amount, short_name
        FROM monitor_gp_sssj_20260429 
        WHERE stock_code = '{code}' 
        ORDER BY time
        LIMIT 5
    """)
    
    rows = cursor.fetchall()
    print(f"  数据条数: {len(rows)}")
    print(f"  前5条原始数据:")
    for i, (time_str, amount, name) in enumerate(rows[:5], 1):
        print(f"    {i}. {time_str} | amount={amount}")
    
    # 2. 计算
    print(f"\n  计算过程:")
    prev_amount = None
    cumulative = 0
    updates = []
    
    cursor.execute(f"""
        SELECT time, amount
        FROM monitor_gp_sssj_20260429 
        WHERE stock_code = '{code}' 
        ORDER BY time
    """)
    
    all_rows = cursor.fetchall()
    
    for time_str, amount in all_rows:
        try:
            amount = float(amount) if amount else 0
        except:
            amount = 0
        
        if prev_amount is None:
            main_net = 0
            print(f"    {time_str}: amount={amount:,.0f}, main_net=0 (首次)")
        else:
            main_net = (amount - prev_amount) * 0.3
            print(f"    {time_str}: amount={amount:,.0f}, delta={amount-prev_amount:,.0f}, main_net={main_net:,.0f}")
        
        cumulative += main_net
        prev_amount = amount
        updates.append((main_net, cumulative, code, time_str))
    
    print(f"\n  最终累计: {cumulative:,.0f}")
    
    # 3. 更新
    print(f"\n  更新数据库...")
    for main_net, cumulative, code, time_str in updates[:3]:  # 只显示前3条
        print(f"    UPDATE {code}@{time_str}: main_net={main_net:,.0f}, cum={cumulative:,.0f}")
    
    # 实际更新
    cursor.executemany("""
        UPDATE monitor_gp_sssj_20260429 
        SET main_net_amount = %s,
            cumulative_main_net = %s
        WHERE stock_code = %s AND time = %s
    """, updates)
    
    conn.commit()
    print(f"  实际更新: {len(updates)} 条")
    
    # 4. 验证
    cursor.execute(f"""
        SELECT time, main_net_amount, cumulative_main_net
        FROM monitor_gp_sssj_20260429 
        WHERE stock_code = '{code}' 
        ORDER BY time
        LIMIT 5
    """)
    
    print(f"\n  验证结果(前5条):")
    for time_str, main, cum in cursor.fetchall():
        print(f"    {time_str}: main_net={main:,.0f}, cum={cum:,.0f}")

# 统计
cursor.execute("""
    SELECT 
        COUNT(*),
        SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END)
    FROM monitor_gp_sssj_20260429
""")

row = cursor.fetchone()

conn.close()

print(f"\n{'='*60}")
print(f"测试完成!")
print(f"  测试股票: {len(test_stocks)}只")
print(f"  当前总填充: {row[1]:,}条 ({row[1]/row[0]*100:.2f}%)")
print(f"{'='*60}")
