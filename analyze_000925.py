#!/usr/bin/env python3
"""分析000925数据问题"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 70)
print("000925 数据分析")
print("=" * 70)

with engine.connect() as conn:
    # 1. 检查实时数据表中的最新数据
    print("\n【问题1】实时数据表 monitor_gp_sssj_20260428")
    print("-" * 70)
    
    df_realtime = pd.read_sql("""
        SELECT time, price, change_pct, main_net_amount, cumulative_main_net
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        ORDER BY time DESC
        LIMIT 10
    """, conn)
    
    print("最新10条记录:")
    print(df_realtime.to_string(index=False))
    
    # 2. 检查15:00:00的数据
    print("\n15:00:00 数据:")
    df_15 = pd.read_sql("""
        SELECT price, change_pct, main_net_amount, cumulative_main_net
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925' AND time = '15:00:00'
    """, conn)
    print(df_15.to_string(index=False) if not df_15.empty else "无记录")
    
    # 3. 检查14:57:00的数据（收盘前最后交易时间）
    print("\n14:57:00 数据:")
    df_1457 = pd.read_sql("""
        SELECT price, change_pct, main_net_amount, cumulative_main_net
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925' AND time = '14:57:00'
    """, conn)
    print(df_1457.to_string(index=False) if not df_1457.empty else "无记录")
    
    # 4. 检查股票上攻排行表
    print("\n\n【问题2】股票上攻排行表 monitor_gp_top30_20260428")
    print("-" * 70)
    
    df_top30 = pd.read_sql("""
        SELECT time, code, name, zf_30, count
        FROM monitor_gp_top30_20260428
        WHERE code = '000925'
        ORDER BY time DESC
        LIMIT 10
    """, conn)
    
    print("最新10条排行记录:")
    print(df_top30.to_string(index=False) if not df_top30.empty else "无记录")
    
    # 5. 检查涨跌幅异常的时间点
    print("\n\n【分析】涨跌幅分布（查看是否有异常值）")
    print("-" * 70)
    
    df_change = pd.read_sql("""
        SELECT 
            time,
            price,
            change_pct,
            CASE 
                WHEN change_pct < -5 THEN '大跌(<-5%)'
                WHEN change_pct < -3 THEN '中跌(-5%~-3%)'
                WHEN change_pct < 0 THEN '小跌(-3%~0%)'
                WHEN change_pct = 0 THEN '平盘'
                WHEN change_pct < 3 THEN '小涨(0~3%)'
                WHEN change_pct < 5 THEN '中涨(3~5%)'
                ELSE '大涨(>5%)'
            END as change_category,
            cumulative_main_net
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        ORDER BY time
    """, conn)
    
    print("涨跌幅分布:")
    print(df_change['change_category'].value_counts().to_string())
    
    # 6. 找出涨跌幅为-4.64的时间点
    print("\n\n【关键】涨跌幅约-4.64的时间点:")
    print("-" * 70)
    
    df_464 = pd.read_sql("""
        SELECT time, price, change_pct, cumulative_main_net
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925' 
        AND ABS(change_pct - (-4.64)) < 0.1
        ORDER BY time
    """, conn)
    
    if not df_464.empty:
        print(f"找到 {len(df_464)} 条记录:")
        print(df_464.to_string(index=False))
    else:
        print("未找到涨跌幅约-4.64的记录")
        
    # 7. 检查最新涨跌幅
    print("\n\n【验证】最新涨跌幅记录:")
    print("-" * 70)
    
    df_latest = pd.read_sql("""
        SELECT time, price, change_pct
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        ORDER BY time DESC
        LIMIT 1
    """, conn)
    
    if not df_latest.empty:
        latest = df_latest.iloc[0]
        print(f"最新时间: {latest['time']}")
        print(f"最新价格: {latest['price']}")
        print(f"最新涨跌幅: {latest['change_pct']}%")
        
        # 计算理论涨跌幅
        try:
            price = float(latest['price'])
            # 假设昨收10.12（根据9.76/-3.56%反推）
            prev_close = price / (1 + latest['change_pct']/100)
            print(f"\n推算昨收: {prev_close:.2f}")
            
            # 验证
            calc_change = (9.76 - prev_close) / prev_close * 100
            print(f"如果价格=9.76，理论涨跌幅: {calc_change:.2f}%")
        except:
            pass

print("\n" + "=" * 70)
print("分析完成")
