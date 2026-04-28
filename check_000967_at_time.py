#!/usr/bin/env python3
"""检查000967在特定时间点的主力净额"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 检查不同时间点的主力净额
    times = ['10:00:00', '11:00:00', '14:00:00', '15:00:00']
    
    print("000967 不同时间点的主力净额")
    print("=" * 60)
    
    for time_str in times:
        result = conn.execute(text(f"""
            SELECT stock_code, time, price, change_pct, main_net_amount, main_behavior
            FROM monitor_gp_sssj_20260428
            WHERE stock_code = '000967'
            AND time <= '{time_str}'
            ORDER BY time DESC
            LIMIT 1
        """)).fetchone()
        
        if result:
            print(f"{result[1]}: 价格={result[2]}, 涨跌幅={result[3]}%, 净额={result[4]:,.0f}, 行为={result[5]}")
    
    print()
    print("=" * 60)
    print("15:00:00 收盘时排行榜中的主力净额")
    
    # 检查15:00:00时该股票在排行榜中的数据
    result2 = conn.execute(text("""
        SELECT code, name, zf_30, amount_now, time
        FROM monitor_gp_top30_20260428
        WHERE code = '000967'
        AND time = '15:00:00'
    """)).fetchone()
    
    if result2:
        print(f"排行榜数据: {result2[0]} {result2[1]}")
        print(f"  涨幅: {result2[2]:.2f}%")
        print(f"  成交额: {result2[3]:,.0f}")
        print(f"  时间: {result2[4]}")
    else:
        print("000967 不在15:00:00的排行榜中")
    
    # 检查该股票15:00:00的主力净额总和
    result3 = conn.execute(text("""
        SELECT 
            SUM(main_net_amount) as total_main_net,
            COUNT(CASE WHEN main_net_amount > 0 THEN 1 END) as inflow_count,
            COUNT(CASE WHEN main_net_amount < 0 THEN 1 END) as outflow_count
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000967'
    """)).fetchone()
    
    print()
    print(f"全天主力净额总和: {result3[0]:,.0f} 元")
    print(f"净流入次数: {result3[1]}")
    print(f"净流出次数: {result3[2]}")
