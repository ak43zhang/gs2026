#!/usr/bin/env python3
"""
填充股票上攻排行所有出现的股票的主力净额数据
包括每个时间点的数据
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from sqlalchemy import create_engine, text

DB_CONFIG = {
    'host': '192.168.0.101',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'gs'
}

TABLE_NAME = "monitor_gp_sssj_20260428"


def get_engine():
    url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    return create_engine(url)


def get_ranking_stocks():
    """获取所有出现在排行榜中的股票"""
    engine = get_engine()
    with engine.connect() as conn:
        # 从 monitor_gp_top30 表获取所有出现过的股票
        stocks = pd.read_sql("""
            SELECT DISTINCT code as stock_code
            FROM monitor_gp_top30_20260428
        """, conn)
        return stocks['stock_code'].tolist()


def calculate_main_force_for_stock(df_stock):
    """计算单只股票的主力净额（Tick价格变化法）"""
    if df_stock.empty:
        return df_stock
    
    df = df_stock.sort_values('time').reset_index(drop=True)
    
    # 转换数值
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    
    # 计算Tick变化
    df['price_diff'] = df['price'].diff().fillna(0)
    df['delta_amount'] = df['amount'].diff().fillna(0)
    df['delta_volume'] = df['volume'].diff().fillna(0)
    
    # 量能比
    median_vol = df['delta_volume'].median()
    if median_vol <= 0:
        median_vol = 20000
    df['volume_ratio'] = df['delta_volume'] / median_vol
    
    # 初始化结果
    df['main_net_amount'] = 0.0
    df['main_behavior'] = '无主力'
    df['main_confidence'] = 0.0
    
    last_direction = 0.0
    
    for idx, row in df.iterrows():
        # 门槛：30万成交额，200手成交量
        if row['delta_amount'] < 300000 or row['delta_volume'] < 20000:
            if row['price_diff'] > 0:
                last_direction = 1.0
            elif row['price_diff'] < 0:
                last_direction = -1.0
            continue
        
        # Tick Rule方向
        if row['price_diff'] > 0:
            direction = 1.0
            last_direction = 1.0
        elif row['price_diff'] < 0:
            direction = -1.0
            last_direction = -1.0
        else:
            direction = last_direction
        
        if direction == 0:
            continue
        
        # 参与系数
        if row['delta_amount'] >= 2000000:
            participation = 1.0
        elif row['delta_amount'] >= 1000000:
            participation = 0.8 + (row['delta_amount'] - 1000000) / 1000000 * 0.2
        elif row['delta_amount'] >= 500000:
            participation = 0.5 + (row['delta_amount'] - 500000) / 500000 * 0.3
        elif row['delta_amount'] >= 300000:
            participation = 0.3 + (row['delta_amount'] - 300000) / 200000 * 0.2
        else:
            participation = 0.0
        
        # 置信度
        if row['delta_amount'] >= 5000000:
            amount_score = 1.0
        elif row['delta_amount'] >= 2000000:
            amount_score = 0.8
        elif row['delta_amount'] >= 1000000:
            amount_score = 0.6
        elif row['delta_amount'] >= 500000:
            amount_score = 0.4
        else:
            amount_score = 0.2
        
        if abs(row['price_diff']) >= 0.05:
            price_score = 1.0
        elif abs(row['price_diff']) >= 0.03:
            price_score = 0.7
        elif abs(row['price_diff']) >= 0.01:
            price_score = 0.4
        else:
            price_score = 0.1
        
        if row['volume_ratio'] >= 10:
            vol_score = 1.0
        elif row['volume_ratio'] >= 5:
            vol_score = 0.7
        elif row['volume_ratio'] >= 2:
            vol_score = 0.4
        else:
            vol_score = 0.2
        
        confidence = round(amount_score * 0.40 + price_score * 0.35 + vol_score * 0.25, 2)
        
        # 行为标签
        if confidence >= 0.7:
            prefix = "大额"
        elif confidence >= 0.4:
            prefix = "中额"
        else:
            prefix = "小额"
        behavior = f"{prefix}买入" if direction > 0 else f"{prefix}卖出"
        
        # 主力净额
        main_net = row['delta_amount'] * direction * participation * confidence
        
        df.at[idx, 'main_net_amount'] = round(main_net, 2)
        df.at[idx, 'main_behavior'] = behavior
        df.at[idx, 'main_confidence'] = round(confidence, 2)
    
    return df


def main():
    print(f"开始填充排行榜股票的主力净额数据")
    print("=" * 60)
    
    engine = get_engine()
    
    # 获取所有排行榜中出现的股票
    ranking_stocks = get_ranking_stocks()
    print(f"排行榜中共有 {len(ranking_stocks)} 只不同股票")
    print()
    
    total_updated = 0
    total_records = 0
    
    for idx, stock_code in enumerate(ranking_stocks, 1):
        try:
            with engine.connect() as conn:
                # 获取该股票的所有数据
                df = pd.read_sql(
                    f"SELECT stock_code, price, volume, amount, time FROM {TABLE_NAME} WHERE stock_code = '{stock_code}' ORDER BY time",
                    conn
                )
                
                if df.empty:
                    continue
                
                total_records += len(df)
                
                # 计算主力净额
                df_result = calculate_main_force_for_stock(df)
                
                # 只更新有主力净额的记录
                df_valid = df_result[df_result['main_net_amount'] != 0]
                
                if df_valid.empty:
                    print(f"{idx}/{len(ranking_stocks)}. {stock_code}: 无主力数据 ({len(df)}条记录)")
                    continue
                
                # 批量更新
                for _, row in df_valid.iterrows():
                    conn.execute(text(f"""
                        UPDATE {TABLE_NAME}
                        SET main_net_amount = {row['main_net_amount']},
                            main_behavior = '{row['main_behavior']}',
                            main_confidence = {row['main_confidence']}
                        WHERE stock_code = '{stock_code}'
                        AND time = '{row['time']}'
                    """))
                
                conn.commit()
                total_updated += len(df_valid)
                
                # 统计
                inflow = (df_valid['main_net_amount'] > 0).sum()
                outflow = (df_valid['main_net_amount'] < 0).sum()
                total_net = df_valid['main_net_amount'].sum()
                
                print(f"{idx}/{len(ranking_stocks)}. {stock_code}: 更新 {len(df_valid)}/{len(df)} 条, 净流入 {inflow} 次, 净流出 {outflow} 次, 净额 {total_net/10000:,.1f} 万")
                
        except Exception as e:
            print(f"{idx}/{len(ranking_stocks)}. {stock_code}: [ERROR] {e}")
            continue
    
    print()
    print("=" * 60)
    print(f"[OK] 完成！共处理 {len(ranking_stocks)} 只股票，{total_records} 条记录，更新 {total_updated} 条")
    print()
    
    # 验证
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as has_main
            FROM {TABLE_NAME}
        """)).fetchone()
        
        print("数据验证:")
        print(f"  总记录数: {result[0]:,}")
        print(f"  有主力净额: {result[1]:,} ({result[1]/result[0]*100:.2f}%)")


if __name__ == "__main__":
    main()
