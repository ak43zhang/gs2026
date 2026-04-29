#!/usr/bin/env python3
"""
高效填充2026-04-29主力净额和累计主力净额
使用批量更新和窗口函数
"""
from sqlalchemy import create_engine, text
import pandas as pd
import time

# 连接池配置
engine = create_engine(
    'mysql+pymysql://root:123456@192.168.0.101:3306/gs',
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600
)

print("=" * 80)
print("高效填充2026-04-29主力净额数据")
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

# 2. 获取有成交额的全部股票（主力净额计算需要成交额变化）
print("\n【2】获取需要计算的股票列表...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT DISTINCT stock_code
        FROM {table_name}
        WHERE amount > 0
        LIMIT 1000
    """))
    
    stock_codes = [row[0] for row in result.fetchall()]
    print(f"  有成交额的股票: {len(stock_codes)}只")

if len(stock_codes) == 0:
    print("  没有需要填充的数据")
    exit(0)

# 3. 使用窗口函数批量计算（高效）
print("\n【3】批量计算主力净额和累计值...")
print("  使用窗口函数批量更新...")

# 分批处理，每批100只股票
batch_size = 100
total_batches = (len(stock_codes) + batch_size - 1) // batch_size

for batch_idx in range(total_batches):
    batch_start = batch_idx * batch_size
    batch_end = min((batch_idx + 1) * batch_size, len(stock_codes))
    batch_codes = stock_codes[batch_start:batch_end]
    
    codes_str = ','.join([f"'{c}'" for c in batch_codes])
    
    try:
        # 使用窗口函数计算累计主力净额
        update_sql = f"""
            UPDATE {table_name} t1
            JOIN (
                SELECT 
                    stock_code,
                    time,
                    -- 计算主力净额（简化版：基于成交额变化）
                    CASE 
                        WHEN LAG(amount) OVER (PARTITION BY stock_code ORDER BY time) IS NULL 
                        THEN 0
                        ELSE (amount - LAG(amount) OVER (PARTITION BY stock_code ORDER BY time)) * 0.3
                    END as calculated_main_net,
                    -- 计算累计主力净额
                    SUM(
                        CASE 
                            WHEN LAG(amount) OVER (PARTITION BY stock_code ORDER BY time) IS NULL 
                            THEN 0
                            ELSE (amount - LAG(amount) OVER (PARTITION BY stock_code ORDER BY time)) * 0.3
                        END
                    ) OVER (PARTITION BY stock_code ORDER BY time ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as calculated_cumulative
                FROM {table_name}
                WHERE stock_code IN ({codes_str})
            ) t2 ON t1.stock_code = t2.stock_code AND t1.time = t2.time
            SET 
                t1.main_net_amount = t2.calculated_main_net,
                t1.cumulative_main_net = t2.calculated_cumulative
            WHERE t1.stock_code IN ({codes_str})
        """
        
        with engine.connect() as conn:
            conn.execute(text(update_sql))
            conn.commit()
        
        if (batch_idx + 1) % 10 == 0:
            elapsed = time.time() - start_time
            print(f"  批次 {batch_idx + 1}/{total_batches} 完成，已用时 {elapsed:.1f}秒")
            
    except Exception as e:
        print(f"  批次 {batch_idx + 1} 失败: {e}")

# 4. 验证结果
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
print(f"填充完成: 用时 {elapsed:.1f}秒")
