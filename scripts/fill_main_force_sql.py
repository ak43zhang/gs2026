#!/usr/bin/env python3
"""
主力净额历史数据填充脚本 - 使用纯SQL计算（最高速）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, text
import pandas as pd

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


def add_columns():
    """添加字段"""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(f"DESCRIBE {TABLE_NAME}"))
        columns = [row[0] for row in result]
        
        if 'main_net_amount' not in columns:
            conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD COLUMN main_net_amount DECIMAL(15,2) DEFAULT 0"))
            print("[OK] 添加字段: main_net_amount")
        
        if 'main_behavior' not in columns:
            conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD COLUMN main_behavior VARCHAR(20) DEFAULT ''"))
            print("[OK] 添加字段: main_behavior")
        
        if 'main_confidence' not in columns:
            conn.execute(text(f"ALTER TABLE {TABLE_NAME} ADD COLUMN main_confidence DECIMAL(3,2) DEFAULT 0"))
            print("[OK] 添加字段: main_confidence")
        
        conn.commit()


def process_by_stock():
    """逐只股票处理（Python计算，批量更新）"""
    engine = get_engine()
    
    # 获取所有股票
    with engine.connect() as conn:
        stocks = pd.read_sql(f"SELECT DISTINCT stock_code FROM {TABLE_NAME} ORDER BY stock_code", conn)
    
    stock_codes = stocks['stock_code'].tolist()
    print(f"共 {len(stock_codes)} 只股票需要处理")
    print()
    
    total_updated = 0
    
    for idx, stock_code in enumerate(stock_codes, 1):
        try:
            with engine.connect() as conn:
                # 获取该股票的所有数据
                df = pd.read_sql(
                    f"SELECT stock_code, price, volume, amount, time FROM {TABLE_NAME} WHERE stock_code = '{stock_code}' ORDER BY time",
                    conn
                )
                
                if len(df) < 2:
                    continue
                
                # 计算Tick变化
                df['price'] = pd.to_numeric(df['price'], errors='coerce')
                df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
                
                df['price_diff'] = df['price'].diff().fillna(0)
                df['delta_amount'] = df['amount'].diff().fillna(0)
                df['delta_volume'] = df['volume'].diff().fillna(0)
                
                # 门槛过滤
                mask = (df['delta_amount'] >= 300000) & (df['delta_volume'] >= 20000)
                df_valid = df[mask].copy()
                
                if df_valid.empty:
                    continue
                
                # 简单方向判断：price_diff > 0 买入, < 0 卖出
                median_vol = df['delta_volume'].median()
                if median_vol <= 0:
                    median_vol = 20000
                
                last_direction = 0
                updates = []
                
                for _, row in df_valid.iterrows():
                    price_diff = row['price_diff']
                    delta_amount = row['delta_amount']
                    delta_volume = row['delta_volume']
                    
                    # 方向判断
                    if price_diff > 0:
                        direction = 1.0
                        last_direction = 1.0
                    elif price_diff < 0:
                        direction = -1.0
                        last_direction = -1.0
                    else:
                        direction = last_direction
                    
                    if direction == 0:
                        continue
                    
                    # 参与系数
                    if delta_amount >= 2000000:
                        participation = 1.0
                    elif delta_amount >= 1000000:
                        participation = 0.8 + (delta_amount - 1000000) / 1000000 * 0.2
                    elif delta_amount >= 500000:
                        participation = 0.5 + (delta_amount - 500000) / 500000 * 0.3
                    elif delta_amount >= 300000:
                        participation = 0.3 + (delta_amount - 300000) / 200000 * 0.2
                    else:
                        participation = 0.0
                    
                    # 简化置信度
                    vol_ratio = delta_volume / median_vol
                    confidence = 0.5
                    if delta_amount >= 1000000:
                        confidence = 0.8
                    elif delta_amount >= 500000:
                        confidence = 0.6
                    
                    main_net = delta_amount * direction * participation * confidence
                    
                    if confidence >= 0.7:
                        prefix = "大额"
                    elif confidence >= 0.4:
                        prefix = "中额"
                    else:
                        prefix = "小额"
                    behavior = f"{prefix}买入" if direction > 0 else f"{prefix}卖出"
                    
                    updates.append({
                        'time': row['time'],
                        'main_net_amount': round(main_net, 2),
                        'main_behavior': behavior,
                        'main_confidence': round(confidence, 2)
                    })
                
                # 批量更新
                if updates:
                    for u in updates:
                        conn.execute(text(f"""
                            UPDATE {TABLE_NAME}
                            SET main_net_amount = {u['main_net_amount']},
                                main_behavior = '{u['main_behavior']}',
                                main_confidence = {u['main_confidence']}
                            WHERE stock_code = '{stock_code}'
                            AND time = '{u['time']}'
                        """))
                    conn.commit()
                    total_updated += len(updates)
                    
                    if idx % 100 == 0:
                        print(f"[进度] {idx}/{len(stock_codes)} 完成，累计更新 {total_updated} 条")
                        
        except Exception as e:
            print(f"[ERROR] {stock_code}: {e}")
            continue
    
    return total_updated


def verify():
    """验证数据"""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as has_main
            FROM {TABLE_NAME}
        """)).fetchone()
        
        print()
        print("验证结果:")
        print(f"  总记录数: {result[0]:,}")
        print(f"  有主力净额: {result[1]:,} ({result[1]/result[0]*100:.2f}%)")
        
        # 查看样本
        result2 = conn.execute(text(f"""
            SELECT stock_code, time, price, main_net_amount, main_behavior
            FROM {TABLE_NAME}
            WHERE main_net_amount != 0
            ORDER BY ABS(main_net_amount) DESC
            LIMIT 10
        """)).fetchall()
        
        print()
        print("主力净额最大的10条记录:")
        for row in result2:
            print(f"  {row[0]} {row[1]}: 价格={row[2]:.2f}, 净额={row[3]:,.0f}, 行为={row[4]}")


if __name__ == "__main__":
    print(f"开始填充 {TABLE_NAME} 的主力净额数据")
    print("=" * 60)
    
    # 添加字段
    add_columns()
    
    # 处理数据
    count = process_by_stock()
    
    # 验证
    verify()
    
    print()
    print("=" * 60)
    print(f"[OK] 完成！共更新 {count} 条记录")
