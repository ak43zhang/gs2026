#!/usr/bin/env python3
"""
主力净额历史数据填充脚本 - Tick价格变化法
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
    'min_amount': 300000,     # 最低成交额门槛: 30万
    'min_volume': 20000,      # 最低成交量门槛: 200手
    'participation_thresholds': {
        'level1': {'amount': 300000,   'ratio': 0.3},
        'level2': {'amount': 500000,   'ratio': 0.5},
        'level3': {'amount': 1000000,  'ratio': 0.8},
        'level4': {'amount': 2000000,  'ratio': 1.0},
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
BATCH_SIZE = 100  # 每批处理100只股票


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


def determine_direction(price_diff: float, last_direction: float) -> float:
    """
    Tick Rule 方向判断
    
    Args:
        price_diff: 当前价格 - 上一个价格
        last_direction: 上一个有方向的tick的方向
    
    Returns:
        direction: +1.0(买入), -1.0(卖出), 或沿用上一方向
    """
    if price_diff > 0:
        return 1.0   # 价格上涨 → 买入主导
    elif price_diff < 0:
        return -1.0  # 价格下跌 → 卖出主导
    else:
        return last_direction  # 价格不变 → 沿用上一方向


def calculate_confidence(delta_amount: float, abs_price_diff: float, volume_ratio: float) -> float:
    """
    三因子置信度计算
    
    置信度 = 成交额因子(40%) + 价格变化因子(35%) + 量能因子(25%)
    """
    # 因子1: 成交额大小（权重40%）
    if delta_amount >= 5_000_000:    # 500万以上
        amount_score = 1.0
    elif delta_amount >= 2_000_000:  # 200万以上
        amount_score = 0.8
    elif delta_amount >= 1_000_000:  # 100万以上
        amount_score = 0.6
    elif delta_amount >= 500_000:    # 50万以上
        amount_score = 0.4
    else:                            # 30-50万
        amount_score = 0.2
    
    # 因子2: 价格变化幅度（权重35%）
    if abs_price_diff >= 0.05:       # 大幅变动
        price_score = 1.0
    elif abs_price_diff >= 0.03:
        price_score = 0.7
    elif abs_price_diff >= 0.01:     # 最小变动单位
        price_score = 0.4
    else:                            # 价格不变
        price_score = 0.1
    
    # 因子3: 量能比（权重25%）
    if volume_ratio >= 10:
        vol_score = 1.0
    elif volume_ratio >= 5:
        vol_score = 0.7
    elif volume_ratio >= 2:
        vol_score = 0.4
    else:
        vol_score = 0.2
    
    confidence = amount_score * 0.40 + price_score * 0.35 + vol_score * 0.25
    return round(confidence, 2)


def label_behavior(direction: float, confidence: float) -> str:
    """简化行为标签"""
    if confidence >= 0.7:
        prefix = "大额"
    elif confidence >= 0.4:
        prefix = "中额"
    else:
        prefix = "小额"
    return f"{prefix}买入" if direction > 0 else f"{prefix}卖出"


def calculate_main_force_for_stock(df_stock: pd.DataFrame, median_delta_volume: float = None) -> pd.DataFrame:
    """
    计算单只股票的主力净额（Tick价格变化法）
    
    流程：
    1. 按时间排序
    2. 计算 price_diff, delta_amount, delta_volume
    3. 门槛过滤
    4. Tick Rule判断方向
    5. 计算置信度
    6. 计算主力净额
    """
    if df_stock.empty:
        return df_stock
    
    df = df_stock.sort_values('time').reset_index(drop=True)
    
    # 转换数值类型
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    
    # 计算差值（Tick Rule核心）
    df['price_diff'] = df['price'].diff().fillna(0)
    df['delta_amount'] = df['amount'].diff().fillna(0)
    df['delta_volume'] = df['volume'].diff().fillna(0)
    
    # 量能比基准
    if median_delta_volume is None:
        median_delta_volume = df['delta_volume'].median()
    if median_delta_volume <= 0:
        median_delta_volume = 20000
    df['volume_ratio'] = df['delta_volume'] / median_delta_volume
    
    # 初始化结果列
    df['main_net_amount'] = 0.0
    df['main_behavior'] = '无主力'
    df['main_confidence'] = 0.0
    
    last_direction = 0.0  # Tick Rule需要记录上一个方向
    
    for idx, row in df.iterrows():
        # 门槛检查
        if row['delta_amount'] < MAIN_FORCE_CONFIG['min_amount'] or \
           row['delta_volume'] < MAIN_FORCE_CONFIG['min_volume']:
            # 不满足门槛，但仍然更新last_direction
            if row['price_diff'] > 0:
                last_direction = 1.0
            elif row['price_diff'] < 0:
                last_direction = -1.0
            continue
        
        # 1. Tick Rule方向判断
        direction = determine_direction(row['price_diff'], last_direction)
        if row['price_diff'] != 0:
            last_direction = direction
        
        # 如果direction仍为0（开盘第一笔），跳过
        if direction == 0:
            continue
        
        # 2. 计算置信度
        confidence = calculate_confidence(
            row['delta_amount'],
            abs(row['price_diff']),
            row['volume_ratio']
        )
        
        # 3. 计算参与系数
        participation = calculate_participation_ratio(row['delta_amount'])
        
        # 4. 计算主力净额
        main_net = row['delta_amount'] * direction * participation * confidence
        
        # 5. 行为标签
        behavior = label_behavior(direction, confidence)
        
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
    
    print(f"开始填充 {TABLE_NAME} 的主力净额数据（Tick价格变化法）")
    print("=" * 60)
    
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
                        SELECT stock_code, short_name, price, volume, amount, time
                        FROM {TABLE_NAME}
                        WHERE stock_code = '{stock_code}'
                        ORDER BY time
                        """,
                        conn
                    )
                    
                    if df.empty:
                        continue
                    
                    # 计算主力净额（Tick价格变化法）
                    df_result = calculate_main_force_for_stock(df)
                    
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
    
    print("=" * 60)
    print(f"[OK] 填充完成，共更新 {total_updated} 条记录")
    return total_updated


def verify_data():
    """验证数据"""
    engine = get_engine()
    
    print()
    print("数据验证")
    print("=" * 60)
    
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
                main_net_amount,
                main_behavior,
                main_confidence
            FROM {TABLE_NAME}
            WHERE stock_code = '000539'
            AND main_net_amount != 0
            ORDER BY time
            LIMIT 10
        """)).fetchall()
        
        if result3:
            print("粤电力A(000539) 主力净额示例:")
            for row in result3:
                print(f"  {row[0]}: 价格={row[1]:.2f}, "
                      f"主力净额={row[2]:,.2f}, 行为={row[3]}, 置信度={row[4]:.2f}")
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


def update_redis_data():
    """同步更新Redis中的数据"""
    print()
    print("同步更新Redis数据")
    print("=" * 60)
    
    try:
        from gs2026.utils import redis_util
        
        engine = get_engine()
        
        # 获取所有时间戳
        with engine.connect() as conn:
            timestamps = pd.read_sql(
                f"SELECT DISTINCT time FROM {TABLE_NAME} ORDER BY time",
                conn
            )['time'].tolist()
        
        print(f"共 {len(timestamps)} 个时间戳需要更新")
        
        updated_count = 0
        for time_str in timestamps:
            try:
                # 从MySQL读取该时间点的完整数据
                with engine.connect() as conn:
                    df = pd.read_sql(
                        f"""
                        SELECT stock_code, short_name, price, change_pct, 
                               volume, amount, time, is_zt, ever_zt,
                               main_net_amount, main_behavior, main_confidence
                        FROM {TABLE_NAME}
                        WHERE time = '{time_str}'
                        """,
                        conn
                    )
                
                if df.empty:
                    continue
                
                # 更新Redis
                redis_key = f"{TABLE_NAME}:{time_str}"
                redis_util.save_dataframe(redis_key, df, use_compression=False)
                updated_count += 1
                
                if updated_count % 100 == 0:
                    print(f"  已更新 {updated_count}/{len(timestamps)} 个时间戳...")
                    
            except Exception as e:
                print(f"  [WARN] 更新 {time_str} 失败: {e}")
                continue
        
        print(f"[OK] Redis同步完成，共更新 {updated_count} 个时间戳")
        
    except Exception as e:
        print(f"[ERROR] Redis更新失败: {e}")
        print("  请手动运行同步脚本或等待系统自动更新")


if __name__ == "__main__":
    # 填充MySQL数据
    count = fill_main_force_data()
    
    # 验证数据
    verify_data()
    
    # 同步到Redis
    update_redis_data()
    
    print()
    print("=" * 60)
    print("[OK] 全部完成！")
