#!/usr/bin/env python3
"""
主力净额历史数据填充脚本
为 monitor_gp_sssj_20260428 表填充主力净额字段
"""

import sys
from pathlib import Path
from datetime import time as dt_time
from typing import Dict, Tuple, List
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 主力净额配置
MAIN_FORCE_CONFIG = {
    'min_amount': 300000,
    'min_volume': 20000,
    'participation_thresholds': {
        'level1': {'amount': 300000, 'ratio': 0.3},
        'level2': {'amount': 500000, 'ratio': 0.5},
        'level3': {'amount': 1000000, 'ratio': 0.8},
        'level4': {'amount': 2000000, 'ratio': 1.0},
    },
}

# 数据库配置
DB_CONFIG = {
    'host': '192.168.0.101',
    'port': 3306,
    'user': 'root',
    'password': '123456',
    'database': 'gs'
}

TABLE_NAME = "monitor_gp_sssj_20260428"
BATCH_SIZE = 50  # 每批处理50只股票


def get_engine():
    """创建数据库连接"""
    url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    return create_engine(url)


def calculate_participation_ratio(delta_amount: float) -> float:
    """计算主力参与系数"""
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


def classify_behavior(price_position: float, price_change_pct: float,
                     volume_ratio: float, time_str: str) -> Tuple[str, float, float]:
    """判断主力行为类型，返回: (behavior_type, direction, confidence)"""
    # 解析时间
    parts = time_str.split(':')
    hour, minute = int(parts[0]), int(parts[1])
    time_of_day = dt_time(hour, minute)
    
    # 场景1：极高位置 + 急涨 + 极端放量 → 拉高出货
    if price_position >= 0.98 and price_change_pct >= 1.0 and volume_ratio >= 5:
        return '拉高出货', -1.0, 0.85
    
    # 场景2：低位 + 放量上涨 → 真正拉升
    if price_position <= 0.3 and price_change_pct >= 0.3 and volume_ratio >= 2:
        return '真正拉升', 1.0, 0.80
    
    # 场景3：低位 + 放量下跌 → 打压吸筹
    if price_position <= 0.3 and price_change_pct <= -0.5 and volume_ratio >= 2:
        return '打压吸筹', 1.0, 0.80
    
    # 场景4：高位 + 放量下跌 → 恐慌抛售
    if price_position >= 0.9 and price_change_pct <= -0.5 and volume_ratio >= 2:
        return '恐慌抛售', -1.0, 0.75
    
    # 场景5：早盘 + 放量上涨 → 疑似拉升
    if dt_time(9, 30) <= time_of_day <= dt_time(10, 0) and volume_ratio >= 2 and price_change_pct >= 0.3:
        return '疑似拉升', 1.0, 0.60
    
    # 场景6：尾盘 + 放量上涨 → 疑似出货
    if dt_time(14, 30) <= time_of_day <= dt_time(15, 0) and volume_ratio >= 2 and price_change_pct >= 0.3:
        return '疑似出货', -1.0, 0.60
    
    # 其他场景：不确定
    if price_change_pct >= 0.5:
        return '不确定', 0.3, 0.30
    elif price_change_pct <= -0.5:
        return '不确定', -0.3, 0.30
    else:
        return '不确定', 0.0, 0.0


def calculate_main_force_for_stock(df_stock: pd.DataFrame, day_high: float, day_low: float) -> pd.DataFrame:
    """计算单只股票的主力净额"""
    if df_stock.empty:
        return df_stock
    
    # 按时间排序
    df = df_stock.sort_values('time').reset_index(drop=True)
    
    # 转换数值类型
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df['change_pct'] = pd.to_numeric(df['change_pct'], errors='coerce')
    
    # 计算周期变化
    df['delta_amount'] = df['amount'].diff().fillna(0)
    df['delta_volume'] = df['volume'].diff().fillna(0)
    df['price_change_pct'] = df['change_pct'].diff().fillna(0)
    
    # 计算价格位置
    price_range = day_high - day_low if day_high > day_low else 1.0
    df['price_position'] = ((df['price'] - day_low) / price_range).clip(0, 1)
    
    # 计算量能比（相对于中位数）
    median_volume = df['delta_volume'].median() if len(df) > 0 else 20000
    if median_volume <= 0:
        median_volume = 20000
    df['volume_ratio'] = df['delta_volume'] / median_volume
    
    # 初始化结果列
    df['main_net_amount'] = 0.0
    df['main_behavior'] = '无主力'
    df['main_confidence'] = 0.0
    
    # 计算主力净额
    for idx, row in df.iterrows():
        # 门槛检查
        if row['delta_amount'] < MAIN_FORCE_CONFIG['min_amount'] or \
           row['delta_volume'] < MAIN_FORCE_CONFIG['min_volume']:
            continue
        
        # 判断主力行为
        behavior, direction, confidence = classify_behavior(
            row['price_position'],
            row['price_change_pct'],
            row['volume_ratio'],
            row['time']
        )
        
        # 计算参与系数
        participation = calculate_participation_ratio(row['delta_amount'])
        
        # 计算主力净额
        if direction != 0:
            main_net = row['delta_amount'] * participation * direction * confidence
        else:
            main_net = 0.0
        
        df.at[idx, 'main_net_amount'] = round(main_net, 2)
        df.at[idx, 'main_behavior'] = behavior
        df.at[idx, 'main_confidence'] = round(confidence, 2)
    
    return df


def add_columns_if_not_exists(engine):
    """添加字段（如果不存在）"""
    with engine.connect() as conn:
        # 检查字段是否存在
        result = conn.execute(text(f"DESCRIBE {TABLE_NAME}"))
        columns = [row[0] for row in result]
        
        if 'main_net_amount' not in columns:
            conn.execute(text(f"""
                ALTER TABLE {TABLE_NAME} 
                ADD COLUMN main_net_amount DECIMAL(15,2) DEFAULT 0 
                COMMENT '主力净额（元），正值=净流入，负值=净流出'
            """))
            print("[OK] 添加字段: main_net_amount")
        
        if 'main_behavior' not in columns:
            conn.execute(text(f"""
                ALTER TABLE {TABLE_NAME} 
                ADD COLUMN main_behavior VARCHAR(20) DEFAULT '' 
                COMMENT '主力行为类型'
            """))
            print("[OK] 添加字段: main_behavior")
        
        if 'main_confidence' not in columns:
            conn.execute(text(f"""
                ALTER TABLE {TABLE_NAME} 
                ADD COLUMN main_confidence DECIMAL(3,2) DEFAULT 0 
                COMMENT '置信度（0-1）'
            """))
            print("[OK] 添加字段: main_confidence")
        
        conn.commit()


def fill_main_force_data():
    """填充主力净额数据"""
    engine = get_engine()
    
    print(f"开始填充 {TABLE_NAME} 的主力净额数据")
    print("-" * 60)
    
    # 步骤1：添加字段
    add_columns_if_not_exists(engine)
    print()
    
    # 步骤2：获取所有股票代码
    with engine.connect() as conn:
        stock_codes = pd.read_sql(
            f"SELECT DISTINCT stock_code FROM {TABLE_NAME}",
            conn
        )['stock_code'].tolist()
    
    print(f"共 {len(stock_codes)} 只股票需要处理")
    print()
    
    # 步骤3：分批处理
    total_updated = 0
    batch_count = (len(stock_codes) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_idx in range(batch_count):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min((batch_idx + 1) * BATCH_SIZE, len(stock_codes))
        batch_codes = stock_codes[start_idx:end_idx]
        
        print(f"处理第 {batch_idx + 1}/{batch_count} 批，共 {len(batch_codes)} 只股票...")
        
        for stock_code in batch_codes:
            try:
                with engine.connect() as conn:
                    # 获取该股票的所有数据
                    df = pd.read_sql(
                        f"""
                        SELECT stock_code, short_name, price, volume, amount, 
                               change_pct, time
                        FROM {TABLE_NAME}
                        WHERE stock_code = '{stock_code}'
                        ORDER BY time
                        """,
                        conn
                    )
                    
                    if df.empty:
                        continue
                    
                    # 计算当日高低点
                    day_high = pd.to_numeric(df['price'], errors='coerce').max()
                    day_low = pd.to_numeric(df['price'], errors='coerce').min()
                    
                    # 计算主力净额
                    df_result = calculate_main_force_for_stock(df, day_high, day_low)
                    
                    # 批量更新到数据库
                    for _, row in df_result.iterrows():
                        update_sql = f"""
                        UPDATE {TABLE_NAME}
                        SET main_net_amount = {row['main_net_amount']},
                            main_behavior = '{row['main_behavior']}',
                            main_confidence = {row['main_confidence']}
                        WHERE stock_code = '{stock_code}'
                        AND time = '{row['time']}'
                        """
                        conn.execute(text(update_sql))
                    
                    conn.commit()
                    total_updated += len(df_result)
                    
            except Exception as e:
                print(f"  [ERROR] 处理股票 {stock_code} 失败: {e}")
                continue
        
        print(f"  [OK] 第 {batch_idx + 1} 批完成，累计更新 {total_updated} 条")
        print()
    
    print("-" * 60)
    print(f"[OK] 填充完成，共更新 {total_updated} 条记录")


def verify_data():
    """验证数据"""
    engine = get_engine()
    
    print()
    print("数据验证")
    print("-" * 60)
    
    with engine.connect() as conn:
        # 验证1：统计有主力参与的数据
        result = conn.execute(text(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN main_net_amount != 0 THEN 1 ELSE 0 END) as has_main_force,
                SUM(CASE WHEN main_net_amount > 0 THEN 1 ELSE 0 END) as main_inflow,
                SUM(CASE WHEN main_net_amount < 0 THEN 1 ELSE 0 END) as main_outflow,
                AVG(ABS(main_net_amount)) as avg_abs_main_net,
                MAX(main_net_amount) as max_main_net,
                MIN(main_net_amount) as min_main_net
            FROM {TABLE_NAME}
        """)).fetchone()
        
        print(f"总记录数: {result[0]:,}")
        print(f"有主力参与的记录: {result[1]:,} ({result[1]/result[0]*100:.1f}%)")
        print(f"主力净流入记录: {result[2]:,}")
        print(f"主力净流出记录: {result[3]:,}")
        print(f"平均主力净额(绝对值): {result[4]:,.2f} 元")
        print(f"最大主力净流入: {result[5]:,.2f} 元")
        print(f"最大主力净流出: {result[6]:,.2f} 元")
        print()
        
        # 验证2：按行为类型统计
        result2 = conn.execute(text(f"""
            SELECT 
                main_behavior,
                COUNT(*) as count,
                AVG(main_net_amount) as avg_amount,
                AVG(main_confidence) as avg_confidence
            FROM {TABLE_NAME}
            WHERE main_net_amount != 0
            GROUP BY main_behavior
            ORDER BY count DESC
        """)).fetchall()
        
        print("主力行为分布:")
        for row in result2:
            print(f"  {row[0]}: {row[1]:,} 次, 平均净额: {row[2]:,.2f} 元, 平均置信度: {row[3]:.2f}")
        print()
        
        # 验证3：查看某只股票的详细数据
        result3 = conn.execute(text(f"""
            SELECT 
                time,
                price,
                change_pct,
                main_net_amount,
                main_behavior,
                main_confidence
            FROM {TABLE_NAME}
            WHERE stock_code = '000001'
            AND main_net_amount != 0
            ORDER BY time
            LIMIT 10
        """)).fetchall()
        
        if result3:
            print("平安银行(000001) 主力净额示例:")
            for row in result3:
                print(f"  {row[0]}: 价格={row[1]:.2f}, 涨跌幅={row[2]:.2f}%, "
                      f"主力净额={row[3]:,.2f}, 行为={row[4]}, 置信度={row[5]:.2f}")
        print()
        
        # 验证4：主力净流入最多的股票
        result4 = conn.execute(text(f"""
            SELECT 
                stock_code,
                short_name,
                SUM(main_net_amount) as total_main_net,
                COUNT(CASE WHEN main_net_amount > 0 THEN 1 END) as inflow_count,
                COUNT(CASE WHEN main_net_amount < 0 THEN 1 END) as outflow_count
            FROM {TABLE_NAME}
            GROUP BY stock_code, short_name
            HAVING SUM(main_net_amount) > 1000000
            ORDER BY total_main_net DESC
            LIMIT 10
        """)).fetchall()
        
        print("主力净流入最多的股票(Top 10):")
        for i, row in enumerate(result4, 1):
            print(f"  {i}. {row[0]} {row[1]}: 净流入={row[2]:,.2f} 元 "
                  f"(流入{row[3]}次, 流出{row[4]}次)")


if __name__ == "__main__":
    fill_main_force_data()
    verify_data()
