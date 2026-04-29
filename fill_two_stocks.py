#!/usr/bin/env python3
"""
为300243和300540填充累计主力净额
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

print("=" * 80)
print("为300243和300540填充累计主力净额")
print("=" * 80)

date = '20260428'
table_name = f"monitor_gp_sssj_{date}"
target_stocks = ['300243', '300540']

for stock_code in target_stocks:
    print(f"\n【处理 {stock_code}】")
    
    with engine.connect() as conn:
        # 1. 检查当前数据
        result = conn.execute(text(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as non_zero_main,
                SUM(CASE WHEN cumulative_main_net != 0 THEN 1 ELSE 0 END) as non_zero_cum
            FROM {table_name}
            WHERE stock_code = '{stock_code}'
        """))
        
        row = result.fetchone()
        print(f"  总记录: {row[0]}")
        print(f"  非零main_net_amount: {row[1]}")
        print(f"  非零cumulative_main_net: {row[2]}")
        
        # 2. 填充累计值
        if row[1] and row[1] > 0:
            print(f"  开始填充...")
            
            update_sql = f"""
                UPDATE {table_name} t1
                JOIN (
                    SELECT 
                        time,
                        SUM(main_net_amount) OVER (
                            ORDER BY time 
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) as calculated_cumulative
                    FROM {table_name}
                    WHERE stock_code = '{stock_code}'
                ) t2 ON t1.time = t2.time
                SET t1.cumulative_main_net = t2.calculated_cumulative
                WHERE t1.stock_code = '{stock_code}'
            """
            
            conn.execute(text(update_sql))
            conn.commit()
            
            # 3. 验证
            result = conn.execute(text(f"""
                SELECT 
                    time,
                    main_net_amount,
                    cumulative_main_net
                FROM {table_name}
                WHERE stock_code = '{stock_code}'
                AND time = '15:00:00'
            """))
            
            row = result.fetchone()
            if row:
                print(f"  15:00:00数据:")
                print(f"    main_net_amount: {row[1]:,.0f}")
                print(f"    cumulative_main_net: {row[2]:,.0f}")
            else:
                print(f"  无15:00:00数据")
        else:
            print(f"  无主力净额数据，跳过")

print(f"\n{'='*80}")
print("填充完成，验证股票上攻排行...")
print("=" * 80)

# 4. 验证上攻排行查询
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')
from gs2026.dashboard2.routes.monitor import _get_change_pct_and_main_net_batch

print("\n【验证查询】")
date_str = '20260428'
time_str = '15:00:00'

change_pct_map, main_net_map = _get_change_pct_and_main_net_batch(date_str, time_str, target_stocks)

for code in target_stocks:
    change_pct = change_pct_map.get(code, '-')
    main_net = main_net_map.get(code, 0)
    print(f"  {code}: 涨跌幅={change_pct}, 主力净额={main_net:,.0f}")

print(f"\n{'='*80}")
