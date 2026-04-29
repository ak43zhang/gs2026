#!/usr/bin/env python3
"""检查000925数据源"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 70)
print("000925 数据源分析")
print("=" * 70)

with engine.connect() as conn:
    # 1. 检查不同时间点的价格
    print("\n【价格变化趋势】")
    print("-" * 70)
    
    df_price = pd.read_sql("""
        SELECT time, price, change_pct
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND time IN ('09:30:00', '10:00:00', '11:00:00', '13:00:00', '14:00:00', '14:57:00', '15:00:00')
        ORDER BY time
    """, conn)
    
    print(df_price.to_string(index=False))
    
    # 2. 计算理论昨收
    print("\n\n【昨收计算】")
    print("-" * 70)
    
    df_latest = pd.read_sql("""
        SELECT price, change_pct
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        ORDER BY time DESC
        LIMIT 1
    """, conn)
    
    if not df_latest.empty:
        price = float(df_latest.iloc[0]['price'])
        change_pct = float(df_latest.iloc[0]['change_pct'])
        
        # 昨收 = 价格 / (1 + 涨跌幅/100)
        prev_close = price / (1 + change_pct / 100)
        
        print(f"最新价格: {price}")
        print(f"最新涨跌幅: {change_pct}%")
        print(f"推算昨收: {prev_close:.2f}")
        print()
        
        # 验证用户说的数据
        user_price = 9.76
        user_change = -3.56
        user_prev_close = user_price / (1 + user_change / 100)
        
        print(f"用户说价格: {user_price}")
        print(f"用户说涨跌幅: {user_change}%")
        print(f"推算昨收: {user_prev_close:.2f}")
        print()
        
        print(f"差异: 昨收不同 ({prev_close:.2f} vs {user_prev_close:.2f})")
    
    # 3. 检查是否有其他数据源
    print("\n\n【检查其他相关表】")
    print("-" * 70)
    
    # 检查是否有其他表包含000925
    tables = ['stock_zh_a_spot', 'stock_zh_a_hist', 'monitor_gp_judge_20260428']
    
    for table in tables:
        try:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE stock_code = '000925' OR code = '000925'"))
            count = result.fetchone()[0]
            print(f"{table}: {count} 条记录")
        except Exception as e:
            print(f"{table}: 查询失败 ({e})")
    
    # 4. 检查实时行情表
    print("\n\n【stock_zh_a_spot 实时行情】")
    print("-" * 70)
    
    try:
        df_spot = pd.read_sql("""
            SELECT * FROM stock_zh_a_spot
            WHERE stock_code = '000925'
            LIMIT 1
        """, conn)
        
        if not df_spot.empty:
            print(f"昨收: {df_spot.iloc[0].get('prev_close', 'N/A')}")
            print(f"最新价: {df_spot.iloc[0].get('price', 'N/A')}")
            print(f"涨跌幅: {df_spot.iloc[0].get('change_pct', 'N/A')}")
        else:
            print("无数据")
    except Exception as e:
        print(f"查询失败: {e}")

print("\n" + "=" * 70)
print("分析完成")
