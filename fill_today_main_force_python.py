#!/usr/bin/env python3
"""
使用Python高效填充2026-04-29主力净额和累计主力净额
"""
from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 连接配置
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("Python高效填充2026-04-29主力净额数据")
print("=" * 80)

date = '20260429'
table_name = f"monitor_gp_sssj_{date}"

start_time = time.time()

# 1. 快速检查当前状态
print("\n【1】检查当前状态...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
    """))
    
    row = result.fetchone()
    print(f"  总记录: {row[0]:,}")
    print(f"  非零main_net_amount: {row[1]:,}")
    print(f"  非零cumulative_main_net: {row[2]:,}")

# 2. 获取需要处理的股票列表
print("\n【2】获取股票列表...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT DISTINCT stock_code
        FROM {table_name}
        WHERE amount > 0
        LIMIT 500
    """))
    
    stock_codes = [row[0] for row in result.fetchall()]
    print(f"  需要处理的股票: {len(stock_codes)}只")

if len(stock_codes) == 0:
    print("  没有需要填充的数据")
    exit(0)

# 3. 分批处理函数
def process_stock_batch(batch_codes):
    """处理一批股票"""
    try:
        codes_str = ','.join([f"'{c}'" for c in batch_codes])
        
        # 查询该批股票的所有数据
        query = f"""
            SELECT stock_code, time, amount, short_name
            FROM {table_name}
            WHERE stock_code IN ({codes_str})
            ORDER BY stock_code, time
        """
        
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return 0
        
        # 转换amount为数值
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        
        # 计算主力净额（成交额变化）
        df['main_net_amount'] = df.groupby('stock_code')['amount'].diff() * 0.3
        df['main_net_amount'] = df['main_net_amount'].fillna(0)
        
        # 计算累计主力净额
        df['cumulative_main_net'] = df.groupby('stock_code')['main_net_amount'].cumsum()
        
        # 批量更新
        updates = []
        for _, row in df.iterrows():
            updates.append({
                'stock_code': row['stock_code'],
                'time': row['time'],
                'main_net_amount': row['main_net_amount'],
                'cumulative_main_net': row['cumulative_main_net']
            })
        
        # 执行批量更新
        with engine.connect() as conn:
            for update in updates:
                conn.execute(text(f"""
                    UPDATE {table_name}
                    SET main_net_amount = :main_net_amount,
                        cumulative_main_net = :cumulative_main_net
                    WHERE stock_code = :stock_code AND time = :time
                """), update)
            conn.commit()
        
        return len(updates)
        
    except Exception as e:
        print(f"  批次失败: {e}")
        return 0

# 4. 多线程并行处理
print("\n【3】多线程并行计算...")
batch_size = 50
total_batches = (len(stock_codes) + batch_size - 1) // batch_size

all_batches = [
    stock_codes[i:i+batch_size] 
    for i in range(0, len(stock_codes), batch_size)
]

total_updated = 0
completed = 0

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(process_stock_batch, batch): i 
               for i, batch in enumerate(all_batches)}
    
    for future in as_completed(futures):
        batch_idx = futures[future]
        try:
            count = future.result()
            total_updated += count
            completed += 1
            
            if completed % 10 == 0:
                elapsed = time.time() - start_time
                print(f"  进度: {completed}/{total_batches} 批次，已更新 {total_updated} 条，用时 {elapsed:.1f}秒")
                
        except Exception as e:
            print(f"  批次 {batch_idx} 异常: {e}")

# 5. 验证结果
print(f"\n【4】验证结果...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
    """))
    
    row = result.fetchone()
    print(f"  总记录: {row[0]:,}")
    print(f"  非零main_net_amount: {row[1]:,}")
    print(f"  非零cumulative_main_net: {row[2]:,}")
    
    # 显示Top 10
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            short_name,
            MAX(time) as latest_time,
            MAX(cumulative_main_net) as max_cumulative
        FROM {table_name}
        WHERE cumulative_main_net != 0
        GROUP BY stock_code, short_name
        ORDER BY ABS(MAX(cumulative_main_net)) DESC
        LIMIT 10
    """))
    
    print("\n  Top 10 累计主力净额:")
    for i, row in enumerate(result.fetchall(), 1):
        print(f"    {i}. {row[0]} {row[1]}: {row[3]:,.0f}")

elapsed = time.time() - start_time
print(f"\n{'='*80}")
print(f"填充完成: 共更新 {total_updated} 条记录，用时 {elapsed:.1f}秒")
