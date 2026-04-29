#!/usr/bin/env python3
"""
排查2026-04-29实时计算流程
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("排查2026-04-29实时计算流程")
print("=" * 80)

date = '20260429'
table_name = f"monitor_gp_sssj_{date}"

# 1. 检查表是否存在
print("\n【1】检查表是否存在...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT COUNT(*) 
        FROM information_schema.tables 
        WHERE table_schema = 'gs' AND table_name = '{table_name}'
    """))
    
    exists = result.fetchone()[0] > 0
    print(f"  表{table_name}: {'存在' if exists else '不存在'}")

if not exists:
    print("  表不存在，退出")
    exit(1)

# 2. 检查表结构
print("\n【2】检查表结构...")
with engine.connect() as conn:
    result = conn.execute(text(f"DESCRIBE {table_name}"))
    columns = [row[0] for row in result.fetchall()]
    print(f"  字段数: {len(columns)}")
    print(f"  有cumulative_main_net: {'cumulative_main_net' in columns}")
    print(f"  有main_net_amount: {'main_net_amount' in columns}")

# 3. 检查最新时间点的数据
print("\n【3】检查最新时间点的数据...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT MAX(time) as latest_time
        FROM {table_name}
    """))
    
    latest_time = result.fetchone()[0]
    print(f"  最新时间: {latest_time}")
    
    if latest_time:
        result = conn.execute(text(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
                SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
            FROM {table_name}
            WHERE time = '{latest_time}'
        """))
        
        row = result.fetchone()
        print(f"  {latest_time}数据:")
        print(f"    总记录: {row[0]}")
        print(f"    非零main_net_amount: {row[1]}")
        print(f"    非零cumulative_main_net: {row[2]}")

# 4. 检查全天数据分布
print("\n【4】检查全天数据分布...")
with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as main_nonzero,
            SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as cum_nonzero
        FROM {table_name}
    """))
    
    row = result.fetchone()
    print(f"  全天总记录: {row[0]:,}")
    print(f"  非零main_net_amount: {row[1]:,}")
    print(f"  非零cumulative_main_net: {row[2]:,}")

# 5. 检查特定股票的数据
print("\n【5】检查特定股票的数据...")
test_codes = ['000001', '000002', '300243', '300540']
codes_str = ','.join([f"'{c}'" for c in test_codes])

with engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT 
            stock_code,
            short_name,
            MAX(time) as latest_time,
            main_net_amount,
            cumulative_main_net
        FROM {table_name}
        WHERE stock_code IN ({codes_str})
        GROUP BY stock_code, short_name
    """))
    
    print(f"  测试股票最新数据:")
    for row in result.fetchall():
        print(f"    {row[0]} {row[1]}: time={row[2]}, main={row[3]}, cum={row[4]}")

print("\n" + "=" * 80)
