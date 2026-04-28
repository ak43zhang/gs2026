#!/usr/bin/env python3
"""测试累计主力净额查询"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

# 测试000967的累计主力净额
with engine.connect() as conn:
    # 不同时间点的累计净额
    times = ['10:00:00', '11:00:00', '14:00:00', '15:00:00']
    
    print("000967 累计主力净额测试")
    print("=" * 60)
    
    for time_str in times:
        result = conn.execute(text(f"""
            SELECT 
                SUM(main_net_amount) as cumulative_main_net,
                COUNT(CASE WHEN main_net_amount > 0 THEN 1 END) as inflow_count,
                COUNT(CASE WHEN main_net_amount < 0 THEN 1 END) as outflow_count
            FROM monitor_gp_sssj_20260428
            WHERE stock_code = '000967'
            AND time <= '{time_str}'
        """)).fetchone()
        
        print(f"{time_str}: 累计净额={result[0]:,.0f}元, 流入{result[1]}次, 流出{result[2]}次")
    
    print()
    print("对比：单条记录 vs 累计值")
    print("-" * 60)
    
    # 15:00:00单条记录
    result2 = conn.execute(text("""
        SELECT main_net_amount
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000967'
        AND time = '15:00:00'
    """)).fetchone()
    
    # 15:00:00累计值
    result3 = conn.execute(text("""
        SELECT SUM(main_net_amount) as cumulative_main_net
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000967'
        AND time <= '15:00:00'
    """)).fetchone()
    
    print(f"15:00:00 单条记录: {result2[0]:,.0f} 元")
    print(f"15:00:00 累计值: {result3[0]:,.0f} 元")
    print(f"差异: {result3[0] - result2[0]:,.0f} 元 ({(result3[0] / result2[0] if result2[0] else 0):.1f}倍)")
