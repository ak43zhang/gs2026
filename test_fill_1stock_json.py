#!/usr/bin/env python3
"""
测试1只股票 - 验证MySQL和Redis双写（JSON格式）
"""
import pymysql
import redis
import json
import pandas as pd

print("=" * 70)
print("测试1只股票 - 验证MySQL和Redis双写（JSON格式）")
print("=" * 70)

# 连接
mysql_conn = pymysql.connect(
    host='192.168.0.101', port=3306, user='root', password='123456',
    database='gs', charset='utf8mb4'
)
mysql_cursor = mysql_conn.cursor()

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

date_str = '20260429'
table_name = f"monitor_gp_sssj_{date_str}"

# 选择1只股票
mysql_cursor.execute(f"""
    SELECT DISTINCT stock_code 
    FROM {table_name}
    WHERE amount > 0
    LIMIT 1
""")

code = mysql_cursor.fetchone()[0]
print(f"\n测试股票: {code}")

# ========== 1. 查询MySQL原始数据 ==========
print(f"\n{'='*70}")
print("【1】MySQL原始数据（前5条）")
print(f"{'='*70}")

mysql_cursor.execute(f"""
    SELECT time, amount, main_net_amount, cumulative_main_net
    FROM {table_name}
    WHERE stock_code = %s
    ORDER BY time
    LIMIT 5
""", (code,))

original_rows = mysql_cursor.fetchall()
for row in original_rows:
    print(f"  {row[0]}: amount={row[1]}, main_net={row[2]}, cum={row[3]}")

# ========== 2. 查询Redis原始数据 ==========
print(f"\n{'='*70}")
print("【2】Redis原始数据（前3条）")
print(f"{'='*70}")

sample_times = [row[0] for row in original_rows[:3]]
for time_str in sample_times:
    redis_key = f"{table_name}:{time_str}"
    data = redis_client.get(redis_key)
    if data:
        df = pd.DataFrame(json.loads(data))
        row_data = df[df['stock_code'] == code]
        if not row_data.empty:
            main_net = row_data['main_net_amount'].values[0] if 'main_net_amount' in row_data.columns else 'N/A'
            cum = row_data['cumulative_main_net'].values[0] if 'cumulative_main_net' in row_data.columns else 'N/A'
            print(f"  {time_str}: main_net={main_net}, cum={cum}")

# ========== 3. 计算并更新 ==========
print(f"\n{'='*70}")
print("【3】计算并更新")
print(f"{'='*70}")

# 查询所有数据
mysql_cursor.execute(f"""
    SELECT time, amount
    FROM {table_name}
    WHERE stock_code = %s
    ORDER BY time
""", (code,))

rows = mysql_cursor.fetchall()
print(f"  数据条数: {len(rows)}")

# 计算
prev_amount = None
cumulative = 0
mysql_updates = []
redis_updates = {}

print(f"\n  计算过程（前10条）:")
for i, (time_str, amount) in enumerate(rows[:10]):
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
    
    mysql_updates.append((main_net, cumulative, code, time_str))
    redis_updates[time_str] = {'main_net_amount': main_net, 'cumulative_main_net': cumulative}

print(f"\n  最终累计: {cumulative:,.0f}")

# 更新MySQL
print(f"\n  更新MySQL...")
mysql_cursor.executemany(f"""
    UPDATE {table_name}
    SET main_net_amount = %s,
        cumulative_main_net = %s
    WHERE stock_code = %s AND time = %s
""", mysql_updates)

mysql_conn.commit()
print(f"  MySQL更新: {len(mysql_updates)} 条")

# 更新Redis
print(f"\n  更新Redis...")
redis_updated = 0
for time_str, data in redis_updates.items():
    redis_key = f"{table_name}:{time_str}"
    json_data = redis_client.get(redis_key)
    
    if json_data:
        df = pd.DataFrame(json.loads(json_data))
        
        # 更新该股票的数据
        mask = df['stock_code'] == code
        if mask.any():
            df.loc[mask, 'main_net_amount'] = data['main_net_amount']
            df.loc[mask, 'cumulative_main_net'] = data['cumulative_main_net']
            
            # 保存回Redis
            redis_client.set(redis_key, df.to_json(orient='records', force_ascii=False))
            redis_updated += 1

print(f"  Redis更新: {redis_updated} 条")

# ========== 4. 验证MySQL更新结果 ==========
print(f"\n{'='*70}")
print("【4】验证MySQL更新结果（前5条）")
print(f"{'='*70}")

mysql_cursor.execute(f"""
    SELECT time, amount, main_net_amount, cumulative_main_net
    FROM {table_name}
    WHERE stock_code = %s
    ORDER BY time
    LIMIT 5
""", (code,))

for row in mysql_cursor.fetchall():
    print(f"  {row[0]}: amount={row[1]}, main_net={row[2]:,.0f}, cum={row[3]:,.0f}")

# ========== 5. 验证Redis更新结果 ==========
print(f"\n{'='*70}")
print("【5】验证Redis更新结果（前3条）")
print(f"{'='*70}")

for time_str in sample_times:
    redis_key = f"{table_name}:{time_str}"
    data = redis_client.get(redis_key)
    if data:
        df = pd.DataFrame(json.loads(data))
        row_data = df[df['stock_code'] == code]
        if not row_data.empty:
            main_net = row_data['main_net_amount'].values[0]
            cum = row_data['cumulative_main_net'].values[0]
            print(f"  {time_str}: main_net={main_net:,.0f}, cum={cum:,.0f}")

# 统计
print(f"\n{'='*70}")
print("【6】最终统计")
print(f"{'='*70}")

mysql_cursor.execute(f"""
    SELECT 
        COUNT(*),
        SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END)
    FROM {table_name}
""")

row = mysql_cursor.fetchone()
print(f"  MySQL总填充: {row[1]:,} 条 ({row[1]/row[0]*100:.2f}%)")

mysql_conn.close()
redis_client.close()

print(f"\n{'='*70}")
print("测试完成!")
print(f"{'='*70}")
