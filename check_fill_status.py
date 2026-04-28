#!/usr/bin/env python3
"""检查填充进度"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 总体进度
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as has_main
        FROM monitor_gp_sssj_20260428
    """)).fetchone()
    
    print(f"总记录数: {result[0]:,}")
    print(f"有主力净额: {result[1]:,} ({result[1]/result[0]*100:.2f}%)")
    print()
    
    # 排行榜股票有多少已有数据
    result2 = conn.execute(text("""
        SELECT COUNT(DISTINCT t1.stock_code) as ranking_stocks_with_data
        FROM monitor_gp_sssj_20260428 t1
        INNER JOIN (
            SELECT DISTINCT code as stock_code FROM monitor_gp_top30_20260428
        ) t2 ON t1.stock_code = t2.stock_code
        WHERE t1.main_net_amount != 0
    """)).fetchone()
    
    result3 = conn.execute(text("""
        SELECT COUNT(DISTINCT code) as total_ranking_stocks
        FROM monitor_gp_top30_20260428
    """)).fetchone()
    
    print(f"排行榜股票总数: {result3[0]}")
    print(f"已有主力净额的排行榜股票: {result2[0]}")
    print()
    
    # 查看样本
    result4 = conn.execute(text("""
        SELECT stock_code, time, price, main_net_amount, main_behavior
        FROM monitor_gp_sssj_20260428
        WHERE main_net_amount != 0
        ORDER BY ABS(main_net_amount) DESC
        LIMIT 5
    """)).fetchall()
    
    print("主力净额最大的5条记录:")
    for row in result4:
        print(f"  {row[0]} {row[1]}: 价格={row[2]}, 净额={row[3]:,.0f}, 行为={row[4]}")
