#!/usr/bin/env python3
"""分析000967的主力净额数据"""
from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 获取000967的基本信息
    print("=" * 60)
    print("000967 分析")
    print("=" * 60)
    
    # 1. 获取该股票的所有数据
    df = pd.read_sql("""
        SELECT stock_code, short_name, price, volume, amount, change_pct, time,
               main_net_amount, main_behavior, main_confidence
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '000967'
        ORDER BY time
    """, conn)
    
    print(f"\n总记录数: {len(df)}")
    print(f"有主力净额的记录: {(df['main_net_amount'] != 0).sum()}")
    print(f"主力净额总和: {df['main_net_amount'].sum():,.2f} 元")
    print(f"涨停状态: {df['change_pct'].max():.2f}%")
    
    # 2. 查看主力净额分布
    print("\n主力净额分布:")
    main_data = df[df['main_net_amount'] != 0].copy()
    if not main_data.empty:
        print(f"  最大单笔净流入: {main_data['main_net_amount'].max():,.2f} 元")
        print(f"  最大单笔净流出: {main_data['main_net_amount'].min():,.2f} 元")
        print(f"  平均单笔净额: {main_data['main_net_amount'].mean():,.2f} 元")
        print(f"  净流入次数: {(main_data['main_net_amount'] > 0).sum()}")
        print(f"  净流出次数: {(main_data['main_net_amount'] < 0).sum()}")
    
    # 3. 查看涨停时间段的数据
    print("\n涨停时间段数据 (change_pct >= 9.5%):")
    zt_data = df[df['change_pct'] >= 9.5].copy()
    print(f"  涨停记录数: {len(zt_data)}")
    if not zt_data.empty:
        print(f"  涨停期间主力净额总和: {zt_data['main_net_amount'].sum():,.2f} 元")
        print(f"  涨停期间有主力参与的记录: {(zt_data['main_net_amount'] != 0).sum()}")
    
    # 4. 查看详细的时间序列（前10条有主力净额的记录）
    print("\n前10条有主力净额的记录:")
    main_records = df[df['main_net_amount'] != 0].head(10)
    for _, row in main_records.iterrows():
        price = float(row['price']) if row['price'] else 0
        change_pct = float(row['change_pct']) if row['change_pct'] else 0
        main_net = float(row['main_net_amount']) if row['main_net_amount'] else 0
        print(f"  {row['time']}: 价格={price:.2f}, 涨跌幅={change_pct:.2f}%, "
              f"净额={main_net:,.0f}, 行为={row['main_behavior']}, 置信度={row['main_confidence']}")
    
    # 5. 分析问题
    print("\n" + "=" * 60)
    print("问题分析")
    print("=" * 60)
    
    # 转换数值类型
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    
    # 计算Tick变化
    df['price_diff'] = df['price'].diff().fillna(0)
    df['delta_amount'] = df['amount'].diff().fillna(0)
    df['delta_volume'] = df['volume'].diff().fillna(0)
    
    # 门槛检查
    threshold_mask = (df['delta_amount'] >= 300000) & (df['delta_volume'] >= 20000)
    print(f"\n满足门槛的记录数: {threshold_mask.sum()} / {len(df)} ({threshold_mask.sum()/len(df)*100:.1f}%)")
    
    # 价格变化分析
    print(f"\n价格变化分析:")
    print(f"  price_diff > 0 (上涨): {(df['price_diff'] > 0).sum()} 次")
    print(f"  price_diff < 0 (下跌): {(df['price_diff'] < 0).sum()} 次")
    print(f"  price_diff = 0 (平盘): {(df['price_diff'] == 0).sum()} 次")
    
    # 涨停期间的价格变化
    if not zt_data.empty:
        zt_indices = zt_data.index
        zt_price_diff = df.loc[zt_indices, 'price_diff']
        print(f"\n涨停期间价格变化:")
        print(f"  上涨次数: {(zt_price_diff > 0).sum()}")
        print(f"  下跌次数: {(zt_price_diff < 0).sum()}")
        print(f"  平盘次数: {(zt_price_diff == 0).sum()}")
    
    # 6. 可能的原因
    print("\n" + "=" * 60)
    print("可能原因")
    print("=" * 60)
    
    reasons = []
    
    # 原因1：涨停后价格不再变化
    if not zt_data.empty:
        zt_price_stable = (zt_data['price'].nunique() == 1)
        if zt_price_stable:
            reasons.append("1. 涨停后价格一直维持在涨停价，price_diff=0，无法判断方向")
    
    # 原因2：成交量太小
    small_volume = (df['delta_volume'] < 20000).sum()
    if small_volume > len(df) * 0.5:
        reasons.append(f"2. 大部分记录成交量小于200手门槛 ({small_volume}/{len(df)})")
    
    # 原因3：成交额太小
    small_amount = (df['delta_amount'] < 300000).sum()
    if small_amount > len(df) * 0.5:
        reasons.append(f"3. 大部分记录成交额小于30万门槛 ({small_amount}/{len(df)})")
    
    # 原因4：涨停后缺乏大单
    if not zt_data.empty:
        zt_main_records = (zt_data['main_net_amount'] != 0).sum()
        if zt_main_records < len(zt_data) * 0.1:
            reasons.append(f"4. 涨停期间缺乏大单交易，主力参与记录极少 ({zt_main_records}/{len(zt_data)})")
    
    if reasons:
        for reason in reasons:
            print(reason)
    else:
        print("需要进一步分析...")
    
    print("\n" + "=" * 60)
