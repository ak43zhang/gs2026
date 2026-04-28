#!/usr/bin/env python3
"""验证 000539 主力净额数据"""
from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    df = pd.read_sql("""
        SELECT time, price, change_pct, main_net_amount, main_behavior, main_confidence
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000539'
        AND main_net_amount != 0
        ORDER BY time
    """, conn)
    
    print(f"000539 main_net_amount != 0 records: {len(df)}")
    print()
    for _, r in df.iterrows():
        t = r['time']
        p = float(r['price'])
        pct = float(r['change_pct'])
        net = float(r['main_net_amount'])
        bh = r['main_behavior']
        cf = float(r['main_confidence'])
        print(f"  {t}: price={p:.2f}, pct={pct:.2f}%, net={net:>12,.0f}, behavior={bh}, conf={cf:.2f}")
    
    print()
    total = df['main_net_amount'].astype(float).sum()
    inflow = df[df['main_net_amount'].astype(float) > 0]['main_net_amount'].astype(float).sum()
    outflow = df[df['main_net_amount'].astype(float) < 0]['main_net_amount'].astype(float).sum()
    print(f"Total net:  {total:>14,.2f}")
    print(f"Inflow:     {inflow:>14,.2f}")
    print(f"Outflow:    {outflow:>14,.2f}")
    
    # 行为分布
    print()
    behavior = pd.read_sql("""
        SELECT main_behavior, COUNT(*) as cnt, 
               SUM(main_net_amount) as total_net,
               AVG(main_confidence) as avg_conf
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000539' AND main_net_amount != 0
        GROUP BY main_behavior ORDER BY cnt DESC
    """, conn)
    print("Behavior distribution:")
    for _, r in behavior.iterrows():
        bh = r['main_behavior']
        cnt = r['cnt']
        tn = float(r['total_net'])
        ac = float(r['avg_conf'])
        print(f"  {bh}: {cnt} times, total_net={tn:>12,.0f}, avg_conf={ac:.2f}")
