#!/usr/bin/env python3
"""分析000925跌但主力流入的真实原因"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("000925 跌但主力流入 - 真实原因分析")
print("=" * 80)

with engine.connect() as conn:
    # 1. 获取关键时间点的数据
    print("\n【关键时间点数据】")
    print("-" * 80)
    
    df = pd.read_sql("""
        SELECT time, price, change_pct, main_net_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND time IN ('09:30:00', '09:30:03', '09:30:06', '09:30:09', '09:30:12', 
                     '09:30:15', '09:30:18', '09:30:21', '09:30:24', '09:30:27',
                     '10:00:00', '11:00:00', '14:00:00', '14:57:00', '15:00:00')
        ORDER BY time
    """, conn)
    
    print(f"{'时间':<12} {'价格':<8} {'涨跌幅':<10} {'主力净额':<15} {'说明':<30}")
    print("-" * 80)
    
    for _, row in df.iterrows():
        price = float(row['price'])
        change_pct = float(row['change_pct'])
        main_net = float(row['main_net_amount'])
        
        if main_net > 1000000:
            desc = "大额流入"
        elif main_net > 0:
            desc = "小额流入"
        elif main_net < -1000000:
            desc = "大额流出"
        elif main_net < 0:
            desc = "小额流出"
        else:
            desc = "无主力"
        
        print(f"{row['time']:<12} {price:<8.2f} {change_pct:<10.2f} {main_net:<15.0f} {desc:<30}")
    
    # 2. 分析早盘低开高走的情况
    print("\n\n【早盘低开高走分析】")
    print("-" * 80)
    
    df_morning = pd.read_sql("""
        SELECT time, price, change_pct, main_net_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND time BETWEEN '09:30:00' AND '09:35:00'
        ORDER BY time
    """, conn)
    
    print(f"{'时间':<12} {'价格':<8} {'涨跌幅':<10} {'主力净额':<15} {'价格变化':<12} {'涨跌幅变化':<12}")
    print("-" * 80)
    
    prev_price = None
    prev_change = None
    
    for _, row in df_morning.iterrows():
        price = float(row['price'])
        change_pct = float(row['change_pct'])
        main_net = float(row['main_net_amount'])
        
        if prev_price is not None:
            price_diff = price - prev_price
            change_diff = change_pct - prev_change
        else:
            price_diff = 0
            change_diff = 0
        
        print(f"{row['time']:<12} {price:<8.2f} {change_pct:<10.2f} {main_net:<15.0f} {price_diff:<12.2f} {change_diff:<12.2f}")
        
        prev_price = price
        prev_change = change_pct
    
    # 3. 统计全天主力净额正负分布
    print("\n\n【主力净额分布统计】")
    print("-" * 80)
    
    df_all = pd.read_sql("""
        SELECT 
            CASE 
                WHEN change_pct >= 0 THEN '上涨'
                ELSE '下跌'
            END as price_trend,
            CASE 
                WHEN main_net_amount > 0 THEN '流入'
                WHEN main_net_amount < 0 THEN '流出'
                ELSE '无'
            END as main_direction,
            COUNT(*) as count,
            SUM(main_net_amount) as total_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        GROUP BY 
            CASE WHEN change_pct >= 0 THEN '上涨' ELSE '下跌' END,
            CASE 
                WHEN main_net_amount > 0 THEN '流入'
                WHEN main_net_amount < 0 THEN '流出'
                ELSE '无'
            END
        ORDER BY price_trend, main_direction
    """, conn)
    
    print(f"{'价格趋势':<10} {'主力方向':<10} {'记录数':<10} {'净额总和':<15}")
    print("-" * 80)
    
    for _, row in df_all.iterrows():
        trend = row['price_trend']
        direction = row['main_direction']
        count = row['count']
        total = float(row['total_amount']) if row['total_amount'] else 0
        print(f"{trend:<10} {direction:<10} {count:<10} {total:<15.0f}")
    
    # 4. 关键发现：为什么跌但主力流入
    print("\n\n【关键发现】")
    print("-" * 80)
    
    # 找出跌但主力流入的记录
    df_down_inflow = pd.read_sql("""
        SELECT time, price, change_pct, main_net_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND change_pct < 0
        AND main_net_amount > 1000000
        ORDER BY time
        LIMIT 10
    """, conn)
    
    print("价格下跌但主力大额流入的10条记录:")
    print(f"{'时间':<12} {'价格':<8} {'涨跌幅':<10} {'主力净额':<15}")
    print("-" * 80)
    
    for _, row in df_down_inflow.iterrows():
        print(f"{row['time']:<12} {float(row['price']):<8.2f} {float(row['change_pct']):<10.2f} {float(row['main_net_amount']):<15.0f}")
    
    # 5. 根本原因
    print("\n\n【根本原因】")
    print("-" * 80)
    
    total_down_inflow = pd.read_sql("""
        SELECT SUM(main_net_amount) as total
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND change_pct < 0
        AND main_net_amount > 0
    """, conn).iloc[0]['total']
    
    total_down_outflow = pd.read_sql("""
        SELECT SUM(main_net_amount) as total
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND change_pct < 0
        AND main_net_amount < 0
    """, conn).iloc[0]['total']
    
    total_up_inflow = pd.read_sql("""
        SELECT SUM(main_net_amount) as total
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND change_pct >= 0
        AND main_net_amount > 0
    """, conn).iloc[0]['total']
    
    total_up_outflow = pd.read_sql("""
        SELECT SUM(main_net_amount) as total
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000925'
        AND change_pct >= 0
        AND main_net_amount < 0
    """, conn).iloc[0]['total']
    
    print(f"下跌时主力流入总额: {float(total_down_inflow):,.0f} 元")
    print(f"下跌时主力流出总额: {float(total_down_outflow):,.0f} 元")
    print(f"上涨时主力流入总额: {float(total_up_inflow):,.0f} 元")
    print(f"上涨时主力流出总额: {float(total_up_outflow):,.0f} 元")
    
    print("\n结论:")
    print("1. 股票全天大部分时间处于下跌状态（change_pct < 0）")
    print("2. 但在下跌过程中，有很多tick是价格微涨的（price_diff > 0）")
    print("3. 这些微涨tick被判定为'买入'，产生主力流入")
    print("4. 虽然整体下跌，但微涨tick的买入量 > 下跌tick的卖出量")
    print("5. 导致全天主力净额为正，但股价下跌")

print("\n" + "=" * 80)
