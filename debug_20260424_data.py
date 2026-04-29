#!/usr/bin/env python3
"""
深度排查2026-04-24数据为空问题
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("2026-04-24 数据为空问题深度排查")
print("=" * 80)

# 1. 检查数据库表是否存在
print("\n【1. 检查数据库表】")
print("=" * 80)

with engine.connect() as conn:
    # 检查表是否存在
    tables = pd.read_sql("""
        SELECT TABLE_NAME 
        FROM information_schema.TABLES 
        WHERE TABLE_SCHEMA = 'gs' 
        AND TABLE_NAME LIKE '%%20260424%%'
    """, conn)
    
    print(f"\n包含20260424的表:")
    if len(tables) > 0:
        for table in tables['TABLE_NAME']:
            print(f"  - {table}")
            
            # 检查表结构
            columns = pd.read_sql(f"""
                SELECT COLUMN_NAME, DATA_TYPE 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = 'gs' 
                AND TABLE_NAME = '{table}'
            """, conn)
            print(f"    字段数: {len(columns)}")
            
            # 检查记录数
            count = pd.read_sql(f"SELECT COUNT(*) as cnt FROM {table}", conn)
            print(f"    记录数: {count.iloc[0]['cnt']}")
    else:
        print("  无相关表！")

# 2. 检查实时数据表
print("\n\n【2. 检查实时数据表 monitor_gp_sssj_20260424】")
print("=" * 80)

with engine.connect() as conn:
    try:
        df = pd.read_sql("SELECT * FROM monitor_gp_sssj_20260424 LIMIT 10", conn)
        print(f"\n表存在，样例数据:")
        print(df.to_string())
        
        # 检查关键字段
        print(f"\n关键字段检查:")
        for col in ['change_pct', 'main_net_amount', 'cumulative_main_net']:
            if col in df.columns:
                null_count = pd.read_sql(f"""
                    SELECT COUNT(*) as cnt 
                    FROM monitor_gp_sssj_20260424 
                    WHERE {col} IS NULL OR {col} = 0
                """, conn)
                total = pd.read_sql("SELECT COUNT(*) as cnt FROM monitor_gp_sssj_20260424", conn)
                print(f"  {col}: NULL/0值 {null_count.iloc[0]['cnt']}/{total.iloc[0]['cnt']} ({null_count.iloc[0]['cnt']/total.iloc[0]['cnt']*100:.1f}%)")
            else:
                print(f"  {col}: 字段不存在！")
    except Exception as e:
        print(f"\n错误: {e}")

# 3. 检查Top30表
print("\n\n【3. 检查Top30表 monitor_gp_top30_20260424】")
print("=" * 80)

with engine.connect() as conn:
    try:
        df = pd.read_sql("SELECT * FROM monitor_gp_top30_20260424 LIMIT 10", conn)
        print(f"\n表存在，样例数据:")
        print(df.to_string())
    except Exception as e:
        print(f"\n错误: {e}")

# 4. 检查Redis数据
print("\n\n【4. 检查Redis数据】")
print("=" * 80)

try:
    import redis
    r = redis.Redis(host='localhost', port=6379, db=0)
    
    # 查找2026-04-24相关的key
    keys = r.keys('*20260424*')
    print(f"\nRedis中包含20260424的key: {len(keys)}个")
    
    if len(keys) > 0:
        for key in keys[:5]:  # 只显示前5个
            print(f"  - {key.decode()}")
            # 检查数据
            data = r.get(key)
            if data:
                print(f"    数据大小: {len(data)} bytes")
    else:
        print("  无相关key！")
        
except Exception as e:
    print(f"\nRedis错误: {e}")

# 5. 检查数据生成流程
print("\n\n【5. 检查数据生成流程】")
print("=" * 80)

print("\n可能的问题:")
print("  1. 2026-04-24不是交易日？")
print("  2. 监控程序未启动？")
print("  3. 数据写入失败？")
print("  4. 表结构变更导致字段缺失？")

# 检查是否是交易日
print("\n\n【6. 检查交易日】")
print("=" * 80)

with engine.connect() as conn:
    try:
        # 检查stock_zh_a_spot表是否有2026-04-24数据
        spot = pd.read_sql("""
            SELECT * FROM stock_zh_a_spot 
            WHERE trade_date = '2026-04-24' 
            LIMIT 5
        """, conn)
        
        if len(spot) > 0:
            print(f"\nstock_zh_a_spot有2026-04-24数据: {len(spot)}条")
        else:
            print(f"\nstock_zh_a_spot无2026-04-24数据")
            
        # 检查最近交易日
        recent = pd.read_sql("""
            SELECT DISTINCT trade_date 
            FROM stock_zh_a_spot 
            ORDER BY trade_date DESC 
            LIMIT 5
        """, conn)
        
        print(f"\n最近交易日:")
        for date in recent['trade_date']:
            print(f"  - {date}")
            
    except Exception as e:
        print(f"\n错误: {e}")

# 7. 对比2026-04-28（正常）
print("\n\n【7. 对比2026-04-28（正常日期）】")
print("=" * 80)

with engine.connect() as conn:
    try:
        df_28 = pd.read_sql("""
            SELECT COUNT(*) as cnt,
                   AVG(change_pct) as avg_change,
                   SUM(main_net_amount) as total_main_net
            FROM monitor_gp_sssj_20260428
        """, conn)
        
        print(f"\n2026-04-28数据:")
        print(f"  记录数: {df_28.iloc[0]['cnt']}")
        print(f"  平均涨跌幅: {df_28.iloc[0]['avg_change']}")
        print(f"  主力净额总和: {df_28.iloc[0]['total_main_net']}")
        
        df_24 = pd.read_sql("""
            SELECT COUNT(*) as cnt,
                   AVG(change_pct) as avg_change,
                   SUM(main_net_amount) as total_main_net
            FROM monitor_gp_sssj_20260424
        """, conn)
        
        print(f"\n2026-04-24数据:")
        print(f"  记录数: {df_24.iloc[0]['cnt']}")
        print(f"  平均涨跌幅: {df_24.iloc[0]['avg_change']}")
        print(f"  主力净额总和: {df_24.iloc[0]['total_main_net']}")
        
    except Exception as e:
        print(f"\n错误: {e}")

print("\n" + "=" * 80)
print("排查完成")
