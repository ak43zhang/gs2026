#!/usr/bin/env python3
"""
主力净额历史数据填充脚本 - Tick价格变化法（高速版）
使用批量UPDATE提高性能
"""

import sys
from pathlib import Path
from datetime import time as dt_time
import pandas as pd
from sqlalchemy import create_engine, text
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 主力净额配置
MAIN_FORCE_CONFIG = {
    'min_amount': 300000,
    'min_volume': 20000,
    'participation_thresholds': {
        'level1': {'amount': 300000,   'ratio': 0.3},
        'level2': {'amount': 500000,   'ratio': 0.5},
        'level3': {'amount': 1000000,  'ratio': 0.8},
        'level4': {'amount': 2000000,  'ratio': 1.0},
    },
}

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
    return create_engine(url, pool_size=10, max_overflow=20)


def calculate_participation_ratio(delta_amount: float) -> float:
    thresholds = MAIN_FORCE_CONFIG['participation_thresholds']
    
    if delta_amount >= thresholds['level4']['amount']:
        return 1.0
    elif delta_amount >= thresholds['level3']['amount']:
        return thresholds['level3']['ratio'] + (delta_amount - thresholds['level3']['amount']) / \
               (thresholds['level4']['amount'] - thresholds['level3']['amount']) * \
               (thresholds['level4']['ratio'] - thresholds['level3']['ratio'])
    elif delta_amount >= thresholds['level2']['amount']:
        return thresholds['level2']['ratio'] + (delta_amount - thresholds['level2']['amount']) / \
               (thresholds['level3']['amount'] - thresholds['level2']['amount']) * \
               (thresholds['level3']['ratio'] - thresholds['level2']['ratio'])
    elif delta_amount >= thresholds['level1']['amount']:
        return thresholds['level1']['ratio'] + (delta_amount - thresholds['level1']['amount']) / \
               (thresholds['level2']['amount'] - thresholds['level1']['amount']) * \
               (thresholds['level2']['ratio'] - thresholds['level1']['ratio'])
    else:
        return 0.0


def determine_direction(price_diff: float, last_direction: float) -> float:
    if price_diff > 0:
        return 1.0
    elif price_diff < 0:
        return -1.0
    else:
        return last_direction


def calculate_confidence(delta_amount: float, abs_price_diff: float, volume_ratio: float) -> float:
    if delta_amount >= 5_000_000:
        amount_score = 1.0
    elif delta_amount >= 2_000_000:
        amount_score = 0.8
    elif delta_amount >= 1_000_000:
        amount_score = 0.6
    elif delta_amount >= 500_000:
        amount_score = 0.4
    else:
        amount_score = 0.2

    if abs_price_diff >= 0.05:
        price_score = 1.0
    elif abs_price_diff >= 0.03:
        price_score = 0.7
    elif abs_price_diff >= 0.01:
        price_score = 0.4
    else:
        price_score = 0.1

    if volume_ratio >= 10:
        vol_score = 1.0
    elif volume_ratio >= 5:
        vol_score = 0.7
    elif volume_ratio >= 2:
        vol_score = 0.4
    else:
        vol_score = 0.2

    return round(amount_score * 0.40 + price_score * 0.35 + vol_score * 0.25, 2)


def label_behavior(direction: float, confidence: float) -> str:
    if confidence >= 0.7:
        prefix = "大额"
    elif confidence >= 0.4:
        prefix = "中额"
    else:
        prefix = "小额"
    return f"{prefix}买入" if direction > 0 else f"{prefix}卖出"


def process_stock_batch(stock_codes_batch):
    """处理一批股票，返回更新数据列表"""
    engine = get_engine()
    updates = []
    
    with engine.connect() as conn:
        for stock_code in stock_codes_batch:
            try:
                df = pd.read_sql(
                    f"SELECT stock_code, price, volume, amount, time FROM {TABLE_NAME} WHERE stock_code = '{stock_code}' ORDER BY time",
                    conn
                )
                
                if df.empty:
                    continue
                
                # 计算Tick价格变化
                df['price'] = pd.to_numeric(df['price'], errors='coerce')
                df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
                
                df['price_diff'] = df['price'].diff().fillna(0)
                df['delta_amount'] = df['amount'].diff().fillna(0)
                df['delta_volume'] = df['volume'].diff().fillna(0)
                
                median_delta_volume = df['delta_volume'].median()
                if median_delta_volume <= 0:
                    median_delta_volume = 20000
                df['volume_ratio'] = df['delta_volume'] / median_delta_volume
                
                last_direction = 0.0
                
                for idx, row in df.iterrows():
                    # 门槛检查
                    if row['delta_amount'] < MAIN_FORCE_CONFIG['min_amount'] or \
                       row['delta_volume'] < MAIN_FORCE_CONFIG['min_volume']:
                        if row['price_diff'] > 0:
                            last_direction = 1.0
                        elif row['price_diff'] < 0:
                            last_direction = -1.0
                        continue
                    
                    direction = determine_direction(row['price_diff'], last_direction)
                    if row['price_diff'] != 0:
                        last_direction = direction
                    
                    if direction == 0:
                        continue
                    
                    confidence = calculate_confidence(row['delta_amount'], abs(row['price_diff']), row['volume_ratio'])
                    participation = calculate_participation_ratio(row['delta_amount'])
                    main_net = row['delta_amount'] * direction * participation * confidence
                    behavior = label_behavior(direction, confidence)
                    
                    updates.append({
                        'stock_code': stock_code,
                        'time': row['time'],
                        'main_net_amount': round(main_net, 2),
                        'main_behavior': behavior,
                        'main_confidence': round(confidence, 2)
                    })
                    
            except Exception as e:
                print(f"[ERROR] {stock_code}: {e}")
                continue
    
    return updates


def batch_update_mysql(updates, batch_size=1000):
    """批量更新MySQL"""
    if not updates:
        return 0
    
    engine = get_engine()
    updated = 0
    
    with engine.connect() as conn:
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i+batch_size]
            
            # 构建批量UPDATE
            cases_amount = []
            cases_behavior = []
            cases_confidence = []
            conditions = []
            
            for u in batch:
                cases_amount.append(f"WHEN '{u['time']}' THEN {u['main_net_amount']}")
                cases_behavior.append(f"WHEN '{u['time']}' THEN '{u['main_behavior']}'")
                cases_confidence.append(f"WHEN '{u['time']}' THEN {u['main_confidence']}")
                conditions.append(f"'{u['time']}'")
            
            sql = f"""
            UPDATE {TABLE_NAME}
            SET 
                main_net_amount = CASE time {' '.join(cases_amount)} END,
                main_behavior = CASE time {' '.join(cases_behavior)} END,
                main_confidence = CASE time {' '.join(cases_confidence)} END
            WHERE stock_code = '{batch[0]['stock_code']}'
            AND time IN ({','.join(conditions)})
            """
            
            try:
                conn.execute(text(sql))
                conn.commit()
                updated += len(batch)
            except Exception as e:
                print(f"[WARN] Batch update failed: {e}")
                # 降级为单条更新
                for u in batch:
                    try:
                        conn.execute(text(f"""
                            UPDATE {TABLE_NAME}
                            SET main_net_amount = {u['main_net_amount']},
                                main_behavior = '{u['main_behavior']}',
                                main_confidence = {u['main_confidence']}
                            WHERE stock_code = '{u['stock_code']}'
                            AND time = '{u['time']}'
                        """))
                        conn.commit()
                        updated += 1
                    except:
                        pass
    
    return updated


def main():
    print(f"开始填充 {TABLE_NAME} 的主力净额数据（Tick价格变化法 - 高速版）")
    print("=" * 60)
    
    engine = get_engine()
    
    # 获取所有股票代码
    with engine.connect() as conn:
        stock_codes = pd.read_sql(f"SELECT DISTINCT stock_code FROM {TABLE_NAME}", conn)['stock_code'].tolist()
    
    print(f"共 {len(stock_codes)} 只股票需要处理")
    print()
    
    # 分批处理（每批10只）
    batch_size = 10
    total_batches = (len(stock_codes) + batch_size - 1) // batch_size
    total_updated = 0
    
    for i in range(total_batches):
        start = i * batch_size
        end = min((i + 1) * batch_size, len(stock_codes))
        batch = stock_codes[start:end]
        
        print(f"处理第 {i+1}/{total_batches} 批 ({start+1}-{end})...", end=' ')
        
        # 处理这批股票
        updates = process_stock_batch(batch)
        
        # 批量更新
        if updates:
            updated = batch_update_mysql(updates)
            total_updated += updated
            print(f"更新 {updated} 条")
        else:
            print("无数据")
        
        if (i + 1) % 10 == 0:
            print(f"  [进度] 已完成 {i+1}/{total_batches} 批，累计更新 {total_updated} 条")
    
    print()
    print("=" * 60)
    print(f"[OK] 填充完成，共更新 {total_updated} 条记录")


if __name__ == "__main__":
    main()
