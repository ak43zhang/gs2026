import json
import math
import re
import sys
import time
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Set

import adata
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, types as sa_types
from sqlalchemy.exc import SAWarning

from gs2026.utils import log_util, pandas_display_config,config_util,mysql_util,redis_util,string_enum
from gs2026.monitor.table_index_manager import add_index_on_first_write, auto_add_index

# ========== 向量化优化导入 ==========
try:
    from gs2026.monitor.vectorized_funcs import (
        calc_is_zt_vectorized,
        calculate_participation_ratio_vectorized
    )
    USE_VECTORIZED = True
except ImportError:
    USE_VECTORIZED = False

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url = config_util.get_config("common.url")
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()

# ========== 行业排行计算优化：模块级缓存 ==========

mysql_util = mysql_util.MysqlTool(url)

# 初始化 Redis 连接（关闭自动解码，以支持压缩）
try:
    redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
except Exception as e:
    logger.error(f"Redis 初始化失败: {e}")
    sys.exit(1)

# ------------------------------
# 配置参数
BATCH_SIZE = 400          # 每批股票数量
MAX_WORKERS = 13           # 并发线程数（可根据需要调整）
INTERVAL = 3              # 轮询间隔（秒）
EXPIRE_SECONDS = 64800    # 过期时间
FETCH_TIMEOUT = 2.5       # 数据采集总超时（秒）- P1-A优化
WINDOW_SECONDS = 15

# ------------------------------
# P2-B: 统一数据清洗配置
# ------------------------------
USE_UNIFIED_CLEAN = True  # 统一数据清洗开关

# 统一清洗标准配置
NORMALIZED_COLUMNS = {
    # 代码字段统一
    'stock_code': {'type': 'str', 'format': 'zfill6', 'aliases': ['code']},
    # 数值字段统一
    'price': {'type': 'float', 'min': 0},
    'volume': {'type': 'float', 'min': 0},
    'amount': {'type': 'float', 'min': 0},
    'change_pct': {'type': 'float'},
    'main_net_amount': {'type': 'float', 'default': 0},
    'cumulative_main_net': {'type': 'float', 'default': 0},
}


def normalize_stock_dataframe(df: pd.DataFrame,
                                required_cols: list = None) -> pd.DataFrame:
    """
    【P2-B优化】统一数据清洗入口函数

    在deal_gp_works中调用一次，后续函数直接使用，避免重复清洗。

    清洗内容：
    1. 代码字段统一为6位字符串（stock_code优先，否则从code映射）
    2. 数值字段统一转换为float（price/volume/amount/change_pct等）
    3. 删除无效数据（price/volume/amount <= 0）
    4. 填充默认值（main_net_amount/cumulative_main_net缺失时填0）
    5. 删除重复代码（保留第一个）

    Args:
        df: 原始DataFrame
        required_cols: 必需列列表，缺失时返回空DataFrame

    Returns:
        pd.DataFrame: 清洗后的DataFrame
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # 1. 统一代码字段（stock_code优先级高于code）
    if 'stock_code' in df.columns:
        df['stock_code'] = (df['stock_code']
                           .astype(str)
                           .str.strip()
                           .str.replace(r'[^0-9]', '', regex=True)
                           .str.zfill(6))
    elif 'code' in df.columns:
        df['stock_code'] = (df['code']
                           .astype(str)
                           .str.strip()
                           .str.replace(r'[^0-9]', '', regex=True)
                           .str.zfill(6))

    # 2. 统一数值字段
    numeric_cols = ['price', 'volume', 'amount', 'change_pct',
                    'main_net_amount', 'cumulative_main_net']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 3. 填充默认值
    if 'main_net_amount' in df.columns:
        df['main_net_amount'] = df['main_net_amount'].fillna(0)
    if 'cumulative_main_net' in df.columns:
        df['cumulative_main_net'] = df['cumulative_main_net'].fillna(0)

    # 4. 删除无效数据（核心字段必须有效）
    if all(c in df.columns for c in ['price', 'volume', 'amount']):
        df = df[(df['price'] > 0) & (df['volume'] > 0) & (df['amount'] > 0)]

    # 5. 删除重复代码（保留第一个）
    if 'stock_code' in df.columns:
        df = df.drop_duplicates(subset=['stock_code'], keep='first')

    # 6. 检查必需列
    if required_cols:
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            logger.warning(f"[P2-B] 缺少必需列: {missing}")
            return pd.DataFrame()

    return df


# 从数据库加载股票代码列表
sql = string_enum.AG_STOCK_SQL5
code_df = pd.read_sql(sql, con=con)
code_list = code_df.values.tolist()
STOCK_CODES = [x[0] for x in code_list]   # 例如 ['600000', '000001', ...]

STOCK_COLUMNS = ['code', 'name', 'zf_30', 'momentum', 'volume_change_rate', 'amount_now',
                   'zf_30_rank','momentum_rank','amount_rank','total_score_rank',
                   'zf_30_pct_rank', 'momentum_pct_rank', 'amount_pct_rank', 'volume_change_pct_rank',
                   'total_score','change_pct','change_pct_zq', 'rq', 'time']

# ========== 行业排行计算：模块级常量和缓存 ==========

# 行业排行结果列
INDUSTRY_RESULT_COLUMNS = [
    'code', 'name', 'count', 'total', 'avg_change_pct', 'avg_price', 'price_quality',
    'raw_ratio', 'smooth_ratio', 'confidence', 'final_score', 'rank', 'rq', 'time'
]

# 价格质量因子默认参数
DEFAULT_PRICE_HALF_LIFE = 15.0  # A股中位价附近
DEFAULT_PRICE_WEIGHT = 0.5      # 温和影响

_industry_mapping_cache = None
_industry_mapping_cache_time = 0
_CACHE_TTL = 300  # 5分钟缓存

# ========== 涨停判断：模块级缓存 ==========
_ever_zt_cache: Set[str] = set()
_ever_zt_cache_date: str = ""

# ========== 主力净额计算：配置参数 ==========
MAIN_FORCE_CONFIG = {
    # 门槛值
    'min_amount': 300000,      # 30万
    'min_volume': 20000,       # 200手
    
    # 参与系数阈值
    'participation_thresholds': {
        'level1': {'amount': 300000, 'ratio': 0.3},
        'level2': {'amount': 500000, 'ratio': 0.5},
        'level3': {'amount': 1000000, 'ratio': 0.8},
        'level4': {'amount': 2000000, 'ratio': 1.0},
    },
    
    # 量能放大系数
    'volume_boost_max': 0.2,
    'volume_boost_ratio': 0.1,
}

# 主力行为类型映射
MAIN_BEHAVIOR_TYPES = {
    '拉高出货': '拉高出货',
    '真正拉升': '真正拉升',
    '打压吸筹': '打压吸筹',
    '恐慌抛售': '恐慌抛售',
    '早盘缩量涨停': '早盘缩量涨停',
    '早盘放量涨停': '早盘放量涨停',
    '尾盘涨停': '尾盘涨停',
    '尾盘巨量涨停': '尾盘巨量涨停',
    '盘中涨停': '盘中涨停',
    '疑似拉升': '疑似拉升',
    '疑似出货': '疑似出货',
    '不确定': '不确定',
    '无主力': '无主力',
}

# 历史统计缓存（用于主力净额计算）
_historical_stats_cache = {}
_historical_stats_cache_date = ""


# ========== 主力净额计算函数 ==========

def calculate_participation_ratio(delta_amount: float) -> float:
    """
    计算主力参与系数
    
    基于成交额大小判断主力参与程度
    
    Args:
        delta_amount: 周期成交额变化（元）
    
    Returns:
        参与系数（0-1）
    """
    thresholds = MAIN_FORCE_CONFIG['participation_thresholds']
    
    if delta_amount >= thresholds['level4']['amount']:  # 200万
        return 1.0
    elif delta_amount >= thresholds['level3']['amount']:  # 100万
        return thresholds['level3']['ratio'] + (delta_amount - thresholds['level3']['amount']) / \
               (thresholds['level4']['amount'] - thresholds['level3']['amount']) * \
               (thresholds['level4']['ratio'] - thresholds['level3']['ratio'])
    elif delta_amount >= thresholds['level2']['amount']:  # 50万
        return thresholds['level2']['ratio'] + (delta_amount - thresholds['level2']['amount']) / \
               (thresholds['level3']['amount'] - thresholds['level2']['amount']) * \
               (thresholds['level3']['ratio'] - thresholds['level2']['ratio'])
    elif delta_amount >= thresholds['level1']['amount']:  # 30万
        return thresholds['level1']['ratio'] + (delta_amount - thresholds['level1']['amount']) / \
               (thresholds['level2']['amount'] - thresholds['level1']['amount']) * \
               (thresholds['level2']['ratio'] - thresholds['level1']['ratio'])
    else:
        return 0.0


def calculate_cumulative_main_net(df: pd.DataFrame, table_name: str, current_time: str) -> pd.DataFrame:
    """
    计算累计主力净额
    
    查询该股票在当前时间之前的累计值，加上当前值得到新的累计值
    
    Args:
        df: 当前时刻数据（包含 main_net_amount）
        table_name: 表名（如 monitor_gp_sssj_20260428）
        current_time: 当前时间（HH:MM:SS）
    
    Returns:
        添加了 cumulative_main_net 列的 DataFrame
    """
    # 初始化累计值为当前值
    df['cumulative_main_net'] = df['main_net_amount'].fillna(0)
    
    try:
        # 从 MySQL 查询上一时刻的累计值
        # 使用子查询获取每只股票最新的累计值
        stock_codes = df['stock_code'].tolist()
        codes_str = ','.join([f"'{c}'" for c in stock_codes])
        
        query = f"""
            SELECT 
                t1.stock_code,
                t1.cumulative_main_net
            FROM {table_name} t1
            INNER JOIN (
                SELECT stock_code, MAX(time) as max_time
                FROM {table_name}
                WHERE time < '{current_time}' AND stock_code IN ({codes_str})
                GROUP BY stock_code
            ) t2 ON t1.stock_code = t2.stock_code AND t1.time = t2.max_time
        """
        
        prev_cumulative = pd.read_sql(query, con=engine)
        
        if not prev_cumulative.empty:
            # 【修复】确保stock_code类型一致（都转为字符串）
            df['stock_code'] = df['stock_code'].astype(str)
            prev_cumulative['stock_code'] = prev_cumulative['stock_code'].astype(str)
            
            # 合并上一时刻的累计值
            df = df.merge(
                prev_cumulative[['stock_code', 'cumulative_main_net']],
                on='stock_code',
                how='left',
                suffixes=('', '_prev')
            )
            
            # 计算新的累计值 = 上一时刻累计值 + 当前值
            df['cumulative_main_net_prev'] = df['cumulative_main_net_prev'].fillna(0)
            df['cumulative_main_net'] = df['cumulative_main_net_prev'] + df['main_net_amount'].fillna(0)
            
            # 删除临时列
            df = df.drop(columns=['cumulative_main_net_prev'], errors='ignore')
        
    except Exception as e:
        logger.error(f"查询上一时刻累计主力净额失败: {e}")
        # 出错时使用当前值作为累计值
        df['cumulative_main_net'] = df['main_net_amount'].fillna(0)
    
    return df


def classify_main_force_behavior(price_position: float, price_change_pct: float, 
                                 volume_ratio: float, time_of_day: dt_time,
                                 is_zt: bool = False) -> dict:
    """
    判断主力行为类型
    
    Args:
        price_position: 价格位置（0-1，基于当日高低点）
        price_change_pct: 价格变化率（%）
        volume_ratio: 成交量比率（相对于均值）
        time_of_day: 当前时间
        is_zt: 是否涨停
    
    Returns:
        dict: {'type': 行为类型, 'direction': 方向系数, 'confidence': 置信度}
    """
    
    # 场景1：极高位置 + 急涨 + 极端放量 → 拉高出货
    if price_position >= 0.98 and price_change_pct >= 1.0 and volume_ratio >= 5:
        return {'type': '拉高出货', 'direction': -1.0, 'confidence': 0.85}
    
    # 场景2：低位 + 放量上涨 → 真正拉升
    if price_position <= 0.3 and price_change_pct >= 0.3 and volume_ratio >= 2:
        return {'type': '真正拉升', 'direction': 1.0, 'confidence': 0.80}
    
    # 场景3：低位 + 放量下跌 → 打压吸筹
    if price_position <= 0.3 and price_change_pct <= -0.5 and volume_ratio >= 2:
        return {'type': '打压吸筹', 'direction': 1.0, 'confidence': 0.80}
    
    # 场景4：高位 + 放量下跌 → 恐慌抛售
    if price_position >= 0.9 and price_change_pct <= -0.5 and volume_ratio >= 2:
        return {'type': '恐慌抛售', 'direction': -1.0, 'confidence': 0.75}
    
    # 场景5：涨停特殊处理
    if is_zt or price_change_pct >= 9.5:
        # 早盘涨停（9:30-10:00）
        if dt_time(9, 30) <= time_of_day <= dt_time(10, 0):
            if volume_ratio <= 0.5:
                return {'type': '早盘缩量涨停', 'direction': 1.0, 'confidence': 0.90}
            else:
                return {'type': '早盘放量涨停', 'direction': 1.0, 'confidence': 0.80}
        # 尾盘涨停（14:30-15:00）
        elif dt_time(14, 30) <= time_of_day <= dt_time(15, 0):
            if volume_ratio >= 3:
                return {'type': '尾盘巨量涨停', 'direction': -1.0, 'confidence': 0.75}
            else:
                return {'type': '尾盘涨停', 'direction': -0.7, 'confidence': 0.60}
        # 盘中涨停
        else:
            return {'type': '盘中涨停', 'direction': 1.0, 'confidence': 0.60}
    
    # 场景6：早盘 + 放量上涨 → 疑似拉升
    if dt_time(9, 30) <= time_of_day <= dt_time(10, 0) and volume_ratio >= 2 and price_change_pct >= 0.3:
        return {'type': '疑似拉升', 'direction': 1.0, 'confidence': 0.60}
    
    # 场景7：尾盘 + 放量上涨 → 疑似出货
    if dt_time(14, 30) <= time_of_day <= dt_time(15, 0) and volume_ratio >= 2 and price_change_pct >= 0.3:
        return {'type': '疑似出货', 'direction': -1.0, 'confidence': 0.60}
    
    # 其他场景：不确定
    if price_change_pct >= 0.5:
        return {'type': '不确定', 'direction': 0.3, 'confidence': 0.30}
    elif price_change_pct <= -0.5:
        return {'type': '不确定', 'direction': -0.3, 'confidence': 0.30}
    else:
        return {'type': '不确定', 'direction': 0.0, 'confidence': 0.0}


def calculate_main_force_net_amount(df_now: pd.DataFrame, df_prev: pd.DataFrame,
                                   day_stats: dict, time_of_day: dt_time) -> pd.DataFrame:
    """
    批量计算主力净额
    
    Args:
        df_now: 当前时刻数据
        df_prev: 上一时刻数据
        day_stats: 当日统计数据（day_high, day_low, day_open）
        time_of_day: 当前时间
    
    Returns:
        DataFrame with main_net_amount, main_behavior, main_confidence columns
    """
    if df_prev is None or df_prev.empty or df_now is None or df_now.empty:
        # 没有上一时刻数据，主力净额为0
        result = pd.DataFrame({
            'stock_code': df_now['stock_code'] if df_now is not None else [],
            'main_net_amount': 0.0,
            'main_behavior': '无主力',
            'main_confidence': 0.0
        })
        return result
    
    # 合并数据
    merged = pd.merge(
        df_now[['stock_code', 'short_name', 'price', 'volume', 'amount', 'change_pct', 'is_zt']],
        df_prev[['stock_code', 'volume', 'amount', 'change_pct']],
        on='stock_code',
        suffixes=('_now', '_prev'),
        how='inner'
    )
    
    if merged.empty:
        return pd.DataFrame({
            'stock_code': df_now['stock_code'],
            'main_net_amount': 0.0,
            'main_behavior': '无主力',
            'main_confidence': 0.0
        })
    
    # 计算周期变化
    merged['delta_amount'] = merged['amount_now'] - merged['amount_prev']
    merged['delta_volume'] = merged['volume_now'] - merged['volume_prev']
    merged['price_change_pct'] = merged['change_pct_now'] - merged['change_pct_prev']
    
    # 门槛过滤
    mask = (merged['delta_amount'] >= MAIN_FORCE_CONFIG['min_amount']) & \
           (merged['delta_volume'] >= MAIN_FORCE_CONFIG['min_volume'])
    valid_data = merged[mask].copy()
    
    if valid_data.empty:
        # 所有数据都不满足门槛
        result = pd.DataFrame({
            'stock_code': merged['stock_code'],
            'main_net_amount': 0.0,
            'main_behavior': '无主力',
            'main_confidence': 0.0
        })
        return result
    
    # 计算价格位置
    day_high = day_stats.get('day_high', valid_data['price'].max())
    day_low = day_stats.get('day_low', valid_data['price'].min())
    price_range = day_high - day_low if day_high > day_low else 1.0
    valid_data['price_position'] = (valid_data['price'] - day_low) / price_range
    valid_data['price_position'] = valid_data['price_position'].clip(0, 1)
    
    # 计算量能比（简化处理，使用固定均值估算）
    avg_volume_estimate = valid_data['delta_volume'].median() if len(valid_data) > 0 else 20000
    valid_data['volume_ratio'] = valid_data['delta_volume'] / avg_volume_estimate if avg_volume_estimate > 0 else 1.0
    
    # 判断主力行为
    behavior_results = valid_data.apply(
        lambda row: classify_main_force_behavior(
            row['price_position'],
            row['price_change_pct'],
            row['volume_ratio'],
            time_of_day,
            row.get('is_zt', 0) == 1
        ),
        axis=1
    )
    
    valid_data['main_behavior'] = behavior_results.apply(lambda x: x['type'])
    valid_data['direction'] = behavior_results.apply(lambda x: x['direction'])
    valid_data['confidence'] = behavior_results.apply(lambda x: x['confidence'])
    
    # 计算参与系数（向量化测试反而更慢，保持apply方式）
    valid_data['participation'] = valid_data['delta_amount'].apply(calculate_participation_ratio)
    
    # 计算主力净额
    valid_data['main_net_amount'] = (
        valid_data['delta_amount'] *
        valid_data['participation'] *
        valid_data['direction'] *
        valid_data['confidence']
    ).round(2)
    
    # 合并结果（包括不满足门槛的数据）
    result = pd.DataFrame({
        'stock_code': merged['stock_code'],
        'main_net_amount': 0.0,
        'main_behavior': '无主力',
        'main_confidence': 0.0
    })
    
    # 更新有效数据的结果
    for _, row in valid_data.iterrows():
        mask = result['stock_code'] == row['stock_code']
        result.loc[mask, 'main_net_amount'] = row['main_net_amount']
        result.loc[mask, 'main_behavior'] = row['main_behavior']
        result.loc[mask, 'main_confidence'] = row['confidence']
    
    return result


def get_day_stats(df: pd.DataFrame) -> dict:
    """
    获取当日统计数据
    
    Args:
        df: 当前时刻数据
    
    Returns:
        dict: {'day_high': 最高价, 'day_low': 最低价, 'day_open': 开盘价}
    """
    if df is None or df.empty:
        return {'day_high': 0, 'day_low': 0, 'day_open': 0}
    
    # 从change_pct和price推算开盘价
    price = pd.to_numeric(df['price'], errors='coerce')
    change_pct = pd.to_numeric(df['change_pct'], errors='coerce')
    
    # 开盘价 = 当前价 / (1 + 涨跌幅)
    open_price = price / (1 + change_pct / 100)
    
    return {
        'day_high': price.max(),
        'day_low': price.min(),
        'day_open': open_price.median() if not open_price.empty else price.median()
    }


def calculate_main_force_and_cumulative(df_now: pd.DataFrame,
                                     df_prev_main: pd.DataFrame,
                                     day_stats: dict,
                                     time_of_day: dt_time) -> pd.DataFrame:
    """
    计算主力净额和累计主力净额（一体化）
    
    使用df_prev_main（上一个有数据的时间点），非15秒周期
    累计净额直接使用df_prev_main中的cumulative_main_net，避免重复查询
    
    Args:
        df_now: 当前时刻数据
        df_prev_main: 上一个有数据的时间点数据（时间戳查询获得）
        day_stats: 当日统计数据
        time_of_day: 当前时间
    
    Returns:
        DataFrame with main_net_amount, main_behavior, main_confidence, cumulative_main_net
    """
    # 初始化字段
    df_now['main_net_amount'] = 0.0
    df_now['main_behavior'] = '无主力'
    df_now['main_confidence'] = 0.0
    df_now['cumulative_main_net'] = 0.0
    
    if df_prev_main is None or df_prev_main.empty:
        return df_now
    
    try:
        # 【P2-B】数据已清洗，这里只做业务需要的类型转换
        # 确保df_prev_main中的数值字段有效
        if 'cumulative_main_net' in df_prev_main.columns:
            df_prev_main['cumulative_main_net'] = pd.to_numeric(
                df_prev_main['cumulative_main_net'], 
                errors='coerce'
            ).fillna(0)
        
        if 'main_net_amount' in df_prev_main.columns:
            df_prev_main['main_net_amount'] = pd.to_numeric(
                df_prev_main['main_net_amount'], 
                errors='coerce'
            ).fillna(0)
        
        # 【修复】确保数值字段为float类型
        numeric_cols = ['price', 'volume', 'amount', 'change_pct']
        for col in numeric_cols:
            if col in df_now.columns:
                df_now[col] = pd.to_numeric(df_now[col], errors='coerce').fillna(0)
            if col in df_prev_main.columns:
                df_prev_main[col] = pd.to_numeric(df_prev_main[col], errors='coerce').fillna(0)
        
        # 1. 计算主力净额
        merged = pd.merge(
            df_now[['stock_code', 'short_name', 'price', 'volume', 'amount', 'change_pct', 'is_zt']],
            df_prev_main[['stock_code', 'volume', 'amount', 'change_pct']],
            on='stock_code',
            suffixes=('_now', '_prev'),
            how='inner'
        )
        
        if merged.empty:
            return df_now
        
        # 计算变化量
        merged['delta_amount'] = merged['amount_now'] - merged['amount_prev']
        merged['delta_volume'] = merged['volume_now'] - merged['volume_prev']
        merged['price_change_pct'] = merged['change_pct_now'] - merged['change_pct_prev']
        
        # 门槛过滤
        mask = (merged['delta_amount'] >= MAIN_FORCE_CONFIG['min_amount']) & \
               (merged['delta_volume'] >= MAIN_FORCE_CONFIG['min_volume'])
        valid_data = merged[mask].copy()
        
        if valid_data.empty:
            return df_now
        
        # 计算价格位置
        day_high = day_stats.get('day_high', valid_data['price'].max())
        day_low = day_stats.get('day_low', valid_data['price'].min())
        price_range = day_high - day_low if day_high > day_low else 1.0
        valid_data['price_position'] = (valid_data['price'] - day_low) / price_range
        valid_data['price_position'] = valid_data['price_position'].clip(0, 1)
        
        # 计算量能比
        avg_volume = valid_data['delta_volume'].median() if len(valid_data) > 0 else 20000
        valid_data['volume_ratio'] = valid_data['delta_volume'] / avg_volume if avg_volume > 0 else 1.0
        
        # 判断主力行为
        behavior_results = valid_data.apply(
            lambda row: classify_main_force_behavior(
                row['price_position'],
                row['price_change_pct'],
                row['volume_ratio'],
                time_of_day,
                row.get('is_zt', 0) == 1
            ),
            axis=1
        )
        
        valid_data['main_behavior'] = behavior_results.apply(lambda x: x['type'])
        valid_data['direction'] = behavior_results.apply(lambda x: x['direction'])
        valid_data['confidence'] = behavior_results.apply(lambda x: x['confidence'])
        
        # 计算参与系数
        valid_data['participation'] = valid_data['delta_amount'].apply(calculate_participation_ratio)
        
        # 计算主力净额
        valid_data['main_net_amount'] = (
            valid_data['delta_amount'] *
            valid_data['participation'] *
            valid_data['direction'] *
            valid_data['confidence']
        ).round(2)
        
        # 【修复】先删除df_now中的冲突列，避免merge时产生_x/_y后缀
        cols_to_drop = ['main_net_amount', 'main_behavior', 'main_confidence']
        for col in cols_to_drop:
            if col in df_now.columns:
                df_now = df_now.drop(columns=[col])
        
        # 合并结果到df_now
        result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'confidence']
        df_now = df_now.merge(valid_data[result_cols], on='stock_code', how='left')
        df_now['main_net_amount'] = df_now['main_net_amount'].fillna(0)
        df_now['main_behavior'] = df_now['main_behavior'].fillna('无主力')
        df_now['main_confidence'] = df_now['confidence'].fillna(0)
        df_now = df_now.drop(columns=['confidence'], errors='ignore')
        
        # 2. 【关键】计算累计主力净额 - 直接使用df_prev_main中的cumulative_main_net
        if 'cumulative_main_net' in df_prev_main.columns:
            # 【修复】删除筛选条件，让所有股票都参与累计计算
            prev_cumulative = df_prev_main[['stock_code', 'cumulative_main_net']].copy()
            
            if not prev_cumulative.empty:
                # 【修复】确保stock_code都是字符串类型（6位补零）
                df_now['stock_code'] = df_now['stock_code'].astype(str).str.strip().str.zfill(6)
                prev_cumulative['stock_code'] = prev_cumulative['stock_code'].astype(str).str.strip().str.zfill(6)
                
                # 合并
                df_now = df_now.merge(
                    prev_cumulative,
                    on='stock_code',
                    how='left',
                    suffixes=('', '_prev')
                )
                
                # 新的累计值 = 上一累计值 + 当前值
                df_now['cumulative_main_net_prev'] = df_now['cumulative_main_net_prev'].fillna(0)
                df_now['cumulative_main_net'] = df_now['cumulative_main_net_prev'] + df_now['main_net_amount']
                df_now = df_now.drop(columns=['cumulative_main_net_prev'], errors='ignore')
        
        non_zero_main = (df_now['main_net_amount'] != 0).sum()
        non_zero_cum = (df_now['cumulative_main_net'] != 0).sum()
        logger.info(f"主力净额计算完成: main={non_zero_main}, cum={non_zero_cum}")
        
    except Exception as e:
        logger.error(f"计算主力净额失败: {e}")
    
    return df_now


def get_zt_limit(code: str, name: str = None) -> float:
    """
    获取股票的涨停幅度限制
    
    Args:
        code: 股票代码
        name: 股票名称
    
    Returns:
        涨停幅度百分比 (如 10.0, 20.0, 5.0)
    """
    # ST股票判断
    if name and ('ST' in name or '*ST' in name):
        return 5.0
    
    # 根据代码前缀判断
    if code.startswith('688'):  # 科创板
        return 20.0
    elif code.startswith(('300', '301')):  # 创业板
        return 20.0
    elif code.startswith(('8', '9')):  # 北交所
        return 30.0
    else:  # 沪深主板
        return 10.0


def calc_is_zt(change_pct: float, code: str, name: str = None) -> int:
    """
    计算是否涨停
    
    Args:
        change_pct: 涨跌幅百分比
        code: 股票代码
        name: 股票名称
    
    Returns:
        1=涨停, 0=未涨停
    """
    if pd.isna(change_pct):
        return 0
    
    zt_limit = get_zt_limit(code, name)
    # 涨停判断：涨跌幅 >= 涨停幅度 - 0.1 (考虑精度误差)
    return 1 if change_pct >= (zt_limit - 0.1) else 0


def update_ever_zt_cache(date_str: str, zt_codes: Set[str]):
    """
    更新曾经涨停缓存
    
    Args:
        date_str: 日期字符串
        zt_codes: 当前涨停的股票代码集合
    """
    global _ever_zt_cache, _ever_zt_cache_date
    
    # 日期变化时清空缓存
    if date_str != _ever_zt_cache_date:
        _ever_zt_cache.clear()
        _ever_zt_cache_date = date_str
    
    # 合并新的涨停股票
    _ever_zt_cache.update(zt_codes)


def is_ever_zt(code: str, date_str: str) -> int:
    """
    判断股票当天是否曾经涨停
    
    Args:
        code: 股票代码
        date_str: 日期字符串
    
    Returns:
        1=当天曾经涨停, 0=当天未涨停
    """
    global _ever_zt_cache, _ever_zt_cache_date
    
    # 日期变化时清空缓存
    if date_str != _ever_zt_cache_date:
        _ever_zt_cache.clear()
        _ever_zt_cache_date = date_str
    
    return 1 if code in _ever_zt_cache else 0


def get_industry_mapping_cached():
    """
    获取股票-行业映射（带内存缓存）
    从 Redis 的 stock_industry_mapping hash 读取
    由 init_stock_industry_mapping_to_redis() 生成
    """
    global _industry_mapping_cache, _industry_mapping_cache_time
    
    now = time.time()
    if _industry_mapping_cache is None or (now - _industry_mapping_cache_time) > _CACHE_TTL:
        try:
            client = redis_util._get_redis_client()
            mapping_data = client.hgetall('stock_industry_mapping')
            
            _industry_mapping_cache = {}
            for stock_code, mapping_json in mapping_data.items():
                stock_code = redis_util._decode_if_bytes(stock_code)
                mapping_json = redis_util._decode_if_bytes(mapping_json)
                data = json.loads(mapping_json)
                _industry_mapping_cache[stock_code] = {
                    'industry_code': data.get('industry_code', ''),
                    'industry_name': data.get('industry_name', '')
                }
            _industry_mapping_cache_time = now
            logger.debug(f"[缓存更新] 行业映射: {len(_industry_mapping_cache)} 条")
        except Exception as e:
            logger.error(f"获取行业映射缓存失败: {e}")
            _industry_mapping_cache = {}
    
    return _industry_mapping_cache


def _ensure_industry_mapping(time_full: str) -> dict:
    """确保行业映射缓存可用，必要时从Redis加载或初始化"""
    mapping = get_industry_mapping_cached()
    if mapping:
        return mapping

    logger.warning(f"[{time_full}] 行业映射缓存为空，尝试刷新...")
    global _industry_mapping_cache, _industry_mapping_cache_time
    _industry_mapping_cache = None
    _industry_mapping_cache_time = 0
    mapping = get_industry_mapping_cached()
    if mapping:
        return mapping

    logger.warning(f"[{time_full}] Redis中无行业映射数据，调用初始化...")
    from gs2026.utils.redis_util import init_stock_industry_mapping_to_redis
    if init_stock_industry_mapping_to_redis():
        _industry_mapping_cache = None
        _industry_mapping_cache_time = 0
        mapping = get_industry_mapping_cached()
        if mapping:
            logger.info(f"[{time_full}] 行业映射初始化成功，共 {len(mapping)} 条")

    return mapping or {}


def _normalize_stock_df(df: pd.DataFrame) -> pd.DataFrame:
    """标准化股票DataFrame列名：stock_code→code, short_name→name, code补零6位"""
    result = df.copy()
    if 'stock_code' in result.columns and 'code' not in result.columns:
        result = result.rename(columns={'stock_code': 'code'})
    if 'short_name' in result.columns and 'name' not in result.columns:
        result = result.rename(columns={'short_name': 'name'})
    if 'code' in result.columns:
        result['code'] = result['code'].astype(str).str.zfill(6)
    return result


def _calc_price_quality(avg_price_series: pd.Series, K: float = DEFAULT_PRICE_HALF_LIFE) -> pd.Series:
    """
    向量化计算价格质量因子：Sigmoid变体，将均价映射到[0.5, 1.0]
    
    price_quality = 0.5 + 0.5 × (1 - exp(-avg_price / K))
    
    Args:
        avg_price_series: 行业均价序列
        K: 半衰期参数（均价=K时，quality≈0.82）
    """
    # 确保均价非负
    safe_price = avg_price_series.clip(lower=0)
    return 0.5 + 0.5 * (1 - np.exp(-safe_price / K))


def calculate_top30_v3(df_now: pd.DataFrame, df_prev: pd.DataFrame, dt: datetime, weights: dict = None) -> pd.DataFrame:
    """
    增强版：计算指定秒数内涨幅与量价动能，采用多因子加权综合评分，返回前30只最具上攻潜力的股票。

    算法升级点：
        - 动态价格区间（根据股票代码前缀区分主板/创业板/科创板/可转债）
        - 多因子加权（涨幅、动能、成交额、可选成交量变化率），百分位数排名后加权
        - 对极端值进行缩尾处理（1%）
        - 增强数据清洗（检查当前时刻数据）
        - 支持窗口时间调整（适应A股/可转债不同噪声水平）
        - 处理空数据及排名并列

    Args:
        df_now (pd.DataFrame): 当前时刻数据。
        df_prev (pd.DataFrame): 前一时刻（当前时刻 - window_seconds）数据。
        dt (datetime): 当前时刻，用于生成日期时间。
        weights (dict): 各因子权重，格式：
            {'zf_30': 0.3, 'momentum': 0.4, 'amount': 0.2, 'volume_change_rate': 0.1}
            若为None则使用默认权重（涨幅30%，动能40%，成交额30%，成交量变化率0%）。

    Returns:
        pd.DataFrame: 包含以下列，按 total_score 升序排列，最多30行。
            - code: 股票代码
            - name: 股票简称
            - zf_30: 窗口涨幅（%）
            - momentum: 动能指标（涨幅 × 成交额变化率 × 10000）
            - volume_change_rate: 成交量变化率（当前成交量 / 前一成交量 - 1）
            - amount_now: 当前成交额
            - zf_30_pct_rank: 涨幅百分位数排名（0~1，越大越好）
            - momentum_pct_rank: 动能百分位数排名
            - amount_pct_rank: 成交额百分位数排名
            - volume_change_pct_rank: 成交量变化率百分位数排名（若权重为0则不输出）
            - total_score: 综合得分（加权百分位数排名之和，值越小排名越前）
            - rq: 日期 YYYYMMDD
            - time: 时间 HH:MM:SS
    """
    # 默认权重（涨幅30%，动能40%，成交额30%，成交量变化率0%）
    if weights is None:
        weights = {'zf_30': 0.5, 'momentum': 0.5, 'amount': 0.0, 'volume_change_rate': 0.0}
    # 确保权重和为1
    assert abs(sum(weights.values()) - 1.0) < 1e-6, "权重之和必须为1"

    # 【P2-B优化】数据已在deal_gp_works中统一清洗，直接使用
    # 只需要本地复制避免修改原始数据
    df_now = df_now.copy()
    df_prev = df_prev.copy()

    # 【P2-B】列名映射：如果上游使用stock_code，映射为code
    if 'code' not in df_now.columns and 'stock_code' in df_now.columns:
        df_now['code'] = df_now['stock_code']
    if 'code' not in df_prev.columns and 'stock_code' in df_prev.columns:
        df_prev['code'] = df_prev['stock_code']

    # 【P2-B】数据已在入口清洗，这里只做业务需要的dropna
    df_now = df_now.dropna(subset=['price', 'volume', 'amount'])
    df_prev = df_prev.dropna(subset=['price', 'volume', 'amount'])

    # 合并两个时刻数据（内连接）
    merged = pd.merge(
        df_now[['code', 'name', 'price', 'volume', 'amount', 'change_pct']],
        df_prev[['code', 'price', 'volume', 'amount', 'change_pct']],
        on='code',
        suffixes=(f'_now', f'_prev'),
        how='inner',
        validate='1:1'  # 假设股票代码唯一
    )
    if merged.empty:
        # 空数据返回空DataFrame（保持列结构）
        return pd.DataFrame(columns=STOCK_COLUMNS)

    # ---------- 动态价格区间 ----------
    # 根据股票代码前缀设置价格上下限（可自定义扩展）
    def get_price_bounds(code_series):
        bounds = []
        for code in code_series:
            if code.startswith(('600','601','603','605','000','001','002')):
                bounds.append((3, 100))      # 主板
            elif code.startswith('300'):
                bounds.append((5, 200))       # 创业板
            elif code.startswith('688'):
                bounds.append((10, 500))       # 科创板
            elif code.startswith(('11','12','123','127')):  # 可转债代码常见前缀
                bounds.append((110, 250))      # 可转债价格范围较宽
            else:
                bounds.append((1, 1000))       # 其他（北交所等）
        return bounds

    price_bounds = get_price_bounds(merged['code'])
    merged['price_min'] = [b[0] for b in price_bounds]
    merged['price_max'] = [b[1] for b in price_bounds]

    # 过滤价格区间：前一时刻价格必须在对应区间内
    merged = merged[
        (merged['price_prev'] >= merged['price_min']) &
        (merged['price_prev'] <= merged['price_max'])
    ].copy()
    merged.drop(columns=['price_min', 'price_max'], inplace=True)

    if merged.empty:
        return pd.DataFrame(columns=STOCK_COLUMNS)

    # ---------- ST股票剔除 ----------
    pattern = re.compile(r'ST|\*ST|退', flags=re.IGNORECASE)
    merged = merged[~merged['name'].str.contains(pattern, na=False)]

    if merged.empty:
        return pd.DataFrame(columns=STOCK_COLUMNS)

    # ---------- 计算指标 ----------
    # 窗口涨幅（百分比）
    merged['zf_30'] = ((merged['price_now'] - merged['price_prev']) / merged['price_prev'] * 100).round(2)

    # 成交额变化率（带缩尾保护）
    amount_prev_abs = merged['amount_prev'].abs()
    merged['amount_change_rate'] = ((merged['amount_now'] - merged['amount_prev']) / (amount_prev_abs + 1e-6)).round(2)
    # 成交量变化率
    merged['volume_change_rate'] = ((merged['volume_now'] - merged['volume_prev']) / (merged['volume_prev'].abs() + 1e-6)).round(2)

    # 对变化率进行缩尾（1%和99%分位数）
    # for col in ['amount_change_rate', 'volume_change_rate']:
    #     lower = merged[col].quantile(0.01)
    #     upper = merged[col].quantile(0.99)
    #     merged[col] = merged[col].astype(float).clip(lower, upper)

    # 动能指标 = 涨幅 × 成交额变化率 × 10000
    merged['momentum'] = (merged['zf_30'] * merged['amount_change_rate'] * 10000).round(2)

    # 当前成交额（便于输出）
    # merged['amount_now'] = merged['amount_now']
    # merged['change_pct_now'] = merged['amount_now']

    # ---------- 对核心因子进行缩尾 ----------
    # for col in ['zf_30', 'momentum', 'amount_now', 'volume_change_rate']:
    #     lower = merged[col].quantile(0.01)
    #     upper = merged[col].quantile(0.99)
    #     merged[col] = merged[col].astype(float).clip(lower, upper)

    # ---------- 计算百分位数排名（越大越好） ----------
    merged['zf_30_rank'] = merged['zf_30'].rank(method='min', ascending=False)
    merged['momentum_rank'] = merged['momentum'].rank(method='min', ascending=False)
    merged['amount_rank'] = merged['amount_now'].rank(method='min', ascending=False)
    merged['zf_30_pct_rank'] = (merged['zf_30'].rank(method='min', pct=True)).round(2)          # 0~1
    merged['momentum_pct_rank'] = (merged['momentum'].rank(method='min', pct=True)).round(2)
    merged['amount_pct_rank'] = (merged['amount_now'].rank(method='min', pct=True)).round(2)
    merged['volume_change_pct_rank'] = (merged['volume_change_rate'].rank(method='min', pct=True)).round(2)


    # ---------- 加权综合得分（值越小越好，即排名越靠前） ----------
    # 由于百分位数是越大越好，我们将其转换为越小越好：1 - pct_rank，然后加权求和
    merged['total_score'] = (
        weights['zf_30'] * (1 - merged['zf_30_pct_rank']) +
        weights['momentum'] * (1 - merged['momentum_pct_rank']) +
        weights['amount'] * (1 - merged['amount_pct_rank']) +
        weights['volume_change_rate'] * (1 - merged['volume_change_pct_rank'])
    ).round(6)

    merged['total_score_rank'] = merged['total_score'].rank(method='min', ascending=True).round(3)

    # ---------- 添加日期时间 ----------
    merged['rq'] = dt.strftime('%Y%m%d')
    merged['time'] = dt.strftime('%H:%M:%S')

    # ---------- 排序与取前30（处理并列） ----------
    # 按 total_score 升序，若相同则按 momentum 降序（认为动能强者优先）
    top_k = math.ceil(len(merged) * 0.05)
    final_df = merged.sort_values(['total_score', 'momentum'], ascending=[True, False]).head(top_k)

    # 【新增】从原始 df_now 中获取主力净额数据
    if 'main_net_amount' in df_now.columns:
        main_net_map = df_now.set_index('code')['main_net_amount'].to_dict()
        final_df['main_net_amount'] = final_df['code'].map(main_net_map).fillna(0)
    else:
        final_df['main_net_amount'] = 0.0

    # 选择并排列输出列
    # output_cols = ['code', 'name', 'zf_30', 'momentum', 'volume_change_rate', 'amount_now',
    #                'zf_30_rank','momentum_rank','amount_rank',
    #                'zf_30_pct_rank', 'momentum_pct_rank', 'amount_pct_rank', 'volume_change_pct_rank',
    #                'total_score', 'rq', 'time']
    # 若成交量变化率权重为0，可选择性不输出该列（为保持统一，仍输出但值可能无意义）
    # final_df = final_df[STOCK_COLUMNS].reset_index(drop=True)

    return final_df

def calculate_top30_v2(df_now: pd.DataFrame, df_prev: pd.DataFrame, dt: datetime,
                       stock_code, short_name, price, volume, amount) -> pd.DataFrame:
    """
    计算30秒内涨幅与动能指标，返回综合排名前30的股票信息。

    算法步骤：
        1. 合并当前时刻（df_now）与30秒前时刻（df_prev）的数据，仅保留共有的股票。
        2. 根据 `stock_code` 参数值动态设置价格筛选区间：
           - 若 `stock_code == 'stock_code'`，价格区间为 [3, 100]
           - 否则价格区间为 [120, 250]
        3. 剔除价格、成交量、成交额为 NaN 或 0 的行，并过滤不在价格区间内的股票。
        4. 剔除名称包含 ST、*ST、退 等字样（不区分大小写）的股票。
        5. 计算指标：
           - `zf_30`：30秒涨幅（百分比）
           - `amount_diff`：成交额差值（当前 - 30秒前）
           - `amount_change_rate`：成交额变化率 = amount_diff / |prev_amount|
           - `momentum`：动能 = zf_30 * amount_change_rate * 10000
        6. 分别取涨幅、动能、当前成交额排名前10%的股票代码（向上取整），取三者交集。
        7. 在交集内计算倒序排名（值越大名次越前，使用 `method='min'`）：
           - `zf_30_rank`、`momentum_rank`、`amount_rank`
        8. 计算综合得分 `all_score = zf_30_rank + momentum_rank`，取得分最小的30只股票。

    Args:
        df_now (pd.DataFrame): 当前时刻的股票数据，必须包含参数中指定的列。
        df_prev (pd.DataFrame): 30秒前的股票数据，列名与 df_now 一致。
        dt (datetime): 当前时刻，用于生成日期（rq）和时间（time）字段。
        stock_code (str): 股票代码的列名（如 'stock_code'）。
        short_name (str): 股票简称的列名（如 'short_name'）。
        price (str): 价格列名（如 'price'）。
        volume (str): 成交量列名（如 'volume'，当日累计量）。
        amount (str): 成交额列名（如 'amount'）。

    Returns:
        pd.DataFrame: 包含以下列的 DataFrame，按 all_score 升序排列（值越小排名越前），
                      最多返回 30 行，若交集不足 30 则返回全部交集。
            - code: 股票代码（str，6位数字，前导补零）
            - name: 股票简称
            - zf_30: 30秒涨幅（百分比，保留两位小数）
            - zf_30_rank: 在交集内的涨幅倒序排名（1 为最高）
            - momentum: 动能指标（可能为负数）
            - momentum_rank: 在交集内的动能倒序排名
            - amount_rank: 在交集内的当前成交额倒序排名
            - all_score: 综合得分 = zf_30_rank + momentum_rank
            - rq: 日期（格式 YYYYMMDD）
            - time: 时间（格式 HH:MM:SS）
    """
    # 复制DataFrame以避免修改原始数据
    df_now = df_now.copy()
    df_prev = df_prev.copy()

    # 统一合并键（股票代码）类型为字符串
    df_now[stock_code] = df_now[stock_code].astype(str).str.zfill(6)
    df_prev[stock_code] = df_prev[stock_code].astype(str).str.zfill(6)

    # 将价格、成交量和成交额列转换为数值类型，无法转换的设为NaN
    df_now[price] = pd.to_numeric(df_now[price], errors='coerce')
    df_prev[price] = pd.to_numeric(df_prev[price], errors='coerce')
    df_now[volume] = pd.to_numeric(df_now[volume], errors='coerce')
    df_prev[volume] = pd.to_numeric(df_prev[volume], errors='coerce')
    df_now[amount] = pd.to_numeric(df_now[amount], errors='coerce')
    df_prev[amount] = pd.to_numeric(df_prev[amount], errors='coerce')

    # 删除价格、成交量或成交额为NaN的行
    df_now = df_now.dropna(subset=[price, volume, amount])
    df_prev = df_prev.dropna(subset=[price, volume, amount])

    # 合并两个时刻的数据（内连接，只保留共同股票）
    merged = pd.merge(
        df_now[[stock_code, short_name, price, volume, amount]],
        df_prev[[stock_code, price, volume, amount]],
        on=stock_code,
        suffixes=('_now', '_prev'),
        how='inner'
    )

    # 根据股票代码列名设置价格区间（保留原有逻辑）
    if stock_code == 'stock_code':
        price_min, price_max = 3, 100
    else:
        price_min, price_max = 110, 250

    # 过滤无效数据及价格范围
    merged = merged[
        (merged[f'{price}_prev'] != 0) & merged[f'{price}_prev'].notna()
        & (merged[f'{volume}_prev'] != 0) & merged[f'{volume}_prev'].notna()
        & (merged[f'{amount}_prev'] != 0) & merged[f'{amount}_prev'].notna()
        & (merged[f'{price}_prev'] >= price_min) & (merged[f'{price}_prev'] <= price_max)
    ].copy()

    # 计算30秒涨幅（百分比）
    merged['zf_30'] = ((merged[f'{price}_now'] - merged[f'{price}_prev']) / merged[f'{price}_prev'] * 100).round(2)

    # 计算30秒成交额变化（差值）和成交额变化率
    merged['amount_diff'] = merged[f'{amount}_now'] - merged[f'{amount}_prev']
    merged['amount_change_rate'] = (merged['amount_diff'] / (merged[f'{amount}_prev'].abs() + 1e-6)).round(2)

    # 计算动能指标：涨幅 × 成交额变化率，放大10000便于观察
    merged['momentum'] = (merged['zf_30'] * merged['amount_change_rate'] * 10000).round(2)

    # 剔除ST股票
    pattern = r'ST|\*ST|退|st|\*st'
    merged = merged[~merged[short_name].str.contains(pattern, na=False, case=True)]

    # 获取涨幅前N和动能前N的股票代码,成交总额前N
    total_rows = len(merged)
    top_k = math.ceil(total_rows * 0.2)  # 前 5% 的行数，向上取整确保至少一行
    gain_codes = merged.nlargest(top_k, 'zf_30')[stock_code].tolist()
    momentum_codes = merged.nlargest(top_k, 'momentum')[stock_code].tolist()
    amount_codes = merged.nlargest(top_k, f'{amount}_now')[stock_code].tolist()

    # 取交集
    union_codes = set(gain_codes) & set(momentum_codes)   # & set(amount_codes)

    # 从merged中提取这些股票的完整记录
    result_df = merged[merged[stock_code].isin(union_codes)].copy()

    # 添加日期和时间字段
    result_df['rq'] = dt.strftime('%Y%m%d')
    result_df['time'] = dt.strftime('%H:%M:%S')

    # 在并集内部计算倒序排名
    # 先计算正序排名（值越大排名越小，即最大值排名为1）
    result_df['zf_30_rank'] = result_df['zf_30'].rank(method='min', ascending=False)
    result_df['momentum_rank'] = result_df['momentum'].rank(method='min', ascending=False)
    result_df['amount_rank'] = result_df[f'{amount}_now'].rank(method='min', ascending=False)

    # 计算综合得分
    result_df['all_score'] = result_df['zf_30_rank'] + result_df['momentum_rank']

    # 重命名股票代码和名称列
    result_df = result_df.rename(columns={stock_code: 'code', short_name: 'name'})

    # 按all_score降序排序取前N，并选择所需字段
    final_df = result_df.nsmallest(30, 'all_score')[
        ['code', 'name', 'zf_30', 'zf_30_rank', 'momentum', 'momentum_rank', 'rq', 'time', 'amount_rank', 'all_score']
    ].reset_index(drop=True)

    return final_df


def save_dataframe(df: pd.DataFrame, table_name: str, time_full: str,
                   expire_seconds: int, use_compression: bool = False) -> None:
    """
    统一保存 DataFrame 到 MySQL 和 Redis。

    Args:
        df (pd.DataFrame): 要存储的 DataFrame。
        table_name (str): 表名（MySQL 表名，也是 Redis 键前缀）。
        time_full (str): 时间点字符串，如 '15:00:00'。
        expire_seconds (int): Redis 数据过期时间（秒）。
        use_compression (bool): 是否对 Redis 数据启用压缩（默认 False）。
    """
    # 1. 写入 MySQL
    try:
        # 自动将 object 列映射为 VARCHAR，避免 TEXT 类型无法建索引
        dtype_map = {}
        for col in df.columns:
            if df[col].dtype == 'object':
                max_len = df[col].astype(str).str.len().max()
                varchar_len = max(10, int(max_len * 1.5)) if max_len and max_len > 0 else 30
                dtype_map[col] = sa_types.VARCHAR(varchar_len)
            elif col in ('is_zt', 'ever_zt'):
                # 涨停字段使用 SMALLINT 类型 (SQLAlchemy没有TINYINT)
                dtype_map[col] = sa_types.SMALLINT()
            elif col == 'main_net_amount':
                # 主力净额使用 DECIMAL(15,2)
                dtype_map[col] = sa_types.DECIMAL(15, 2)
            elif col == 'cumulative_main_net':
                # 累计主力净额使用 DECIMAL(15,2)
                dtype_map[col] = sa_types.DECIMAL(15, 2)
            elif col == 'main_confidence':
                # 置信度使用 DECIMAL(3,2)
                dtype_map[col] = sa_types.DECIMAL(3, 2)
        
        df.to_sql(table_name, con=engine, if_exists='append', index=False, 
                  method='multi', dtype=dtype_map)
        logger.info(f"已写入 MySQL 表 {table_name}，共 {len(df)} 条记录")
    except Exception as e:
        logger.error(f"MySQL 写入失败: {e}")

    # 2. 写入 Redis
    redis_util.save_dataframe_to_redis(df, table_name, time_full, expire_seconds, use_compression)


def batch_codes(codes, batch_size):
    """
    将代码列表分批，每批最多 batch_size 个。

    Args:
        codes (list): 股票代码列表。
        batch_size (int): 每批最大数量。

    Returns:
        list of list: 分批后的代码列表。
    """
    return [codes[i:i + batch_size] for i in range(0, len(codes), batch_size)]


# ========== P1-A: 模块级线程池（避免每次创建新线程池） ==========
_fetch_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix='fetch')

# ========== P1-B: 存储专用线程池 + dtype缓存 ==========
_storage_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='storage')
_dtype_cache = {}
_dtype_cache_lock = threading.Lock()


def _get_dtype_map(df: pd.DataFrame, table_name: str) -> dict:
    """
    获取DataFrame列到SQL类型的映射（带缓存）。
    
    首次调用时计算并缓存，后续直接返回缓存结果。
    避免每次save_dataframe都重新遍历所有列计算dtype。
    
    Args:
        df: DataFrame（仅首次调用时使用）
        table_name: 表名（作为缓存键）
    
    Returns:
        dict: 列名到SQLAlchemy类型的映射
    """
    with _dtype_cache_lock:
        if table_name in _dtype_cache:
            return _dtype_cache[table_name]
    
    dtype_map = {}
    for col in df.columns:
        if df[col].dtype == 'object':
            max_len = df[col].astype(str).str.len().max()
            varchar_len = max(10, int(max_len * 1.5)) if max_len and max_len > 0 else 30
            dtype_map[col] = sa_types.VARCHAR(varchar_len)
        elif col in ('is_zt', 'ever_zt'):
            dtype_map[col] = sa_types.SMALLINT()
        elif col == 'main_net_amount':
            dtype_map[col] = sa_types.DECIMAL(15, 2)
        elif col == 'cumulative_main_net':
            dtype_map[col] = sa_types.DECIMAL(15, 2)
        elif col == 'main_confidence':
            dtype_map[col] = sa_types.DECIMAL(3, 2)
    
    with _dtype_cache_lock:
        _dtype_cache[table_name] = dtype_map
    
    return dtype_map


def _write_mysql_async(df: pd.DataFrame, table_name: str, dtype_map: dict) -> None:
    """
    MySQL写入（在后台线程执行）。
    
    Args:
        df: 要写入的DataFrame（已深拷贝）
        table_name: MySQL表名
        dtype_map: 列类型映射
    """
    try:
        df.to_sql(table_name, con=engine, if_exists='append',
                  index=False, method='multi', dtype=dtype_map)
        logger.info(f"[异步存储] MySQL写入完成: {table_name}，{len(df)}条")
    except Exception as e:
        logger.error(f"[异步存储] MySQL写入失败: {table_name}, {e}")


def _write_redis_async(df: pd.DataFrame, table_name: str, time_full: str,
                       expire_seconds: int, use_compression: bool) -> None:
    """
    Redis写入（在后台线程执行）。
    
    Args:
        df: 要写入的DataFrame（已深拷贝）
        table_name: Redis键前缀
        time_full: 时间点字符串
        expire_seconds: 过期时间（秒）
        use_compression: 是否压缩
    """
    try:
        redis_util.save_dataframe_to_redis(df, table_name, time_full,
                                           expire_seconds, use_compression)
    except Exception as e:
        logger.error(f"[异步存储] Redis写入失败: {table_name}:{time_full}, {e}")


def save_dataframe_async(df: pd.DataFrame, table_name: str, time_full: str,
                         expire_seconds: int, use_compression: bool = False) -> None:
    """
    异步存储DataFrame到MySQL和Redis（非阻塞）。
    
    将MySQL和Redis写入提交到后台线程池，主线程立即返回。
    使用深拷贝避免主线程后续修改影响后台写入。
    dtype映射使用缓存，同一表名只计算一次。
    
    Args:
        df: 要存储的DataFrame
        table_name: 表名
        time_full: 时间点字符串
        expire_seconds: Redis过期时间（秒）
        use_compression: 是否对Redis数据启用压缩
    """
    # 获取dtype映射（带缓存，避免重复计算）
    dtype_map = _get_dtype_map(df, table_name)
    
    # 深拷贝DataFrame（避免主线程后续修改影响后台写入）
    df_copy = df.copy()
    
    # 提交到后台线程池（非阻塞，立即返回）
    _storage_executor.submit(_write_mysql_async, df_copy, table_name, dtype_map)
    _storage_executor.submit(_write_redis_async, df_copy, table_name, time_full,
                             expire_seconds, use_compression)
    
    logger.info(f"[异步存储] 已提交: {table_name}:{time_full}，{len(df)}条")


def shutdown_storage() -> None:
    """
    程序退出前等待后台存储完成。
    
    确保所有提交的异步写入任务都执行完毕，避免数据丢失。
    """
    logger.info("等待后台存储任务完成...")
    _storage_executor.shutdown(wait=True)
    _fetch_executor.shutdown(wait=False)
    logger.info("后台存储任务已全部完成")


# 注册退出钩子，确保程序退出时等待存储完成
import atexit
atexit.register(shutdown_storage)


def fetch_batch(batch):
    """
    调用API获取单批数据，返回DataFrame。

    Args:
        batch (list): 一批股票代码。

    Returns:
        pd.DataFrame: 获取的数据，如果失败则返回空 DataFrame。
    """
    try:
        # 假设list_market_current返回DataFrame或可转为DataFrame的结构
        df = adata.stock.market.list_market_current(batch)
        return df
    except Exception as e:
        print(f"批次 {batch[:5]}... 请求失败: {e}")
        return pd.DataFrame()  # 返回空DataFrame避免中断


def fetch_all_concurrently(codes):
    """
    并发获取所有代码的数据，合并后返回一个DataFrame。
    
    【P1-A优化】使用模块级线程池 + 超时控制：
    - 总超时FETCH_TIMEOUT秒，超时后使用已获取的部分数据
    - 模块级线程池避免每次创建新线程
    - 单批失败不影响其他批次

    Args:
        codes (list): 所有股票代码列表。

    Returns:
        pd.DataFrame: 合并后的数据，如果没有任何数据则返回空 DataFrame。
    """
    batches = batch_codes(codes, BATCH_SIZE)
    all_data = []

    # 使用模块级线程池提交所有批次
    futures = {_fetch_executor.submit(fetch_batch, batch): batch for batch in batches}
    
    try:
        # as_completed带总超时，超时后停止等待
        for future in as_completed(futures, timeout=FETCH_TIMEOUT):
            try:
                df = future.result(timeout=0.5)  # 单批结果获取超时0.5秒
                if not df.empty:
                    all_data.append(df)
            except TimeoutError:
                logger.warning("[P1-A] 单批数据获取超时，跳过")
                continue
            except Exception as e:
                logger.warning(f"[P1-A] 单批数据获取异常: {e}")
                continue
    except TimeoutError:
        # 总超时，记录已获取和未完成的批次数
        done_count = sum(1 for f in futures if f.done())
        logger.warning(f"[P1-A] 数据采集总超时({FETCH_TIMEOUT}s)，"
                      f"已完成{done_count}/{len(futures)}批")

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    else:
        return pd.DataFrame()


def write_to_mysql(df, table_name):
    """
    将DataFrame写入MySQL表（使用 engine.begin 自动提交事务）。

    Args:
        df (pd.DataFrame): 要写入的数据。
        table_name (str): 目标表名。
    """
    if df is None or df.empty:
        logger.error("数据为空，跳过写入")
    else:
        with engine.begin() as conn:
            df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
            logger.info(f"已写入 {len(df)} 行到表 {table_name}")


# 集合竞价时间段配置
AUCTION_PERIODS = [
    (dt_time(9, 25), dt_time(9, 30)),   # 早盘集合竞价
    (dt_time(14, 57), dt_time(15, 0)),  # 尾盘集合竞价
]

# 记录是否已在当前集合竞价时段获取过数据
_auction_data_fetched = {
    'morning': False,   # 9:25-9:30
    'afternoon': False, # 14:57-15:00
}


def is_in_auction_period(t: dt_time) -> tuple:
    """
    检查当前时间是否在集合竞价时段内

    Args:
        t: 时间对象

    Returns:
        (is_auction: bool, period_name: str or None)
    """
    for start, end in AUCTION_PERIODS:
        if start <= t <= end:
            period_name = 'morning' if start.hour == 9 else 'afternoon'
            return True, period_name
    return False, None


def reset_auction_flags():
    """
    重置集合竞价获取标志
    每天开盘前调用
    """
    global _auction_data_fetched
    _auction_data_fetched = {
        'morning': False,
        'afternoon': False,
    }


def is_trading_time(dt):
    """
    判断给定时间是否在A股交易时段内（周一至周五，9:30-11:30 和 13:00-15:00）。

    Args:
        dt (datetime): 待判断的时间。

    Returns:
        bool: True 如果在交易时段内，否则 False。
    """
    if dt.weekday() >= 5:  # 周六、周日
        return False
    t = dt.time()
    # 上午交易时段
    if dt_time(9, 25) <= t <= dt_time(11, 30):
        return True
    # 下午交易时段
    if dt_time(13, 0) <= t <= dt_time(15, 0):
        return True
    return False


def next_trading_start(dt):
    """
    计算下一个交易开始时间（从当前时间之后最近的交易时段起点）。

    Args:
        dt (datetime): 当前时间。

    Returns:
        datetime: 下一个交易开始时间点。
    """
    # 如果当前在交易时段内，理论上不应调用此函数，但为安全返回当前
    if is_trading_time(dt):
        return dt

    # 定义交易时段边界
    morning_start = dt_time(9, 25)
    morning_end = dt_time(11, 30)
    afternoon_start = dt_time(13, 0)
    afternoon_end = dt_time(15, 0)

    current_date = dt.date()
    current_time = dt.time()

    # 情况1：当前时间在上午开始之前（即9:30之前）
    if current_time < morning_start:
        candidate = datetime.combine(current_date, morning_start)
        # 如果当天是周末，需要跳到下周一
        if candidate.weekday() >= 5:
            days_to_monday = (7 - candidate.weekday()) % 7
            candidate += timedelta(days=days_to_monday)
        return candidate

    # 情况2：当前时间在上午交易时段内（正常情况下不会进入此分支，但保留）
    if morning_start <= current_time <= morning_end:
        return dt

    # 情况3：当前时间在上午结束后、下午开始前（11:30 - 13:00）
    if morning_end < current_time < afternoon_start:
        candidate = datetime.combine(current_date, afternoon_start)
        # 下午开始时间不可能落在周末，因为上午交易时段已排除周末
        return candidate

    # 情况4：当前时间在下午交易时段内（正常情况下不会进入）
    if afternoon_start <= current_time <= afternoon_end:
        return dt

    # 情况5：当前时间在下午结束后（15:00之后）
    # 下一个交易开始是下一个工作日的9:30
    next_day = current_date + timedelta(days=1)
    candidate = datetime.combine(next_day, morning_start)
    # 如果下一天是周末，继续向后找周一
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def is_past_1500(dt):
    """
    判断给定时间是否超过当天的15:00。

    Args:
        dt (datetime): 待判断的时间。

    Returns:
        bool: True 如果 dt > 当天15:00，否则 False。
    """
    return dt > datetime.combine(dt.date(), dt_time(15, 0))


def get_market_stats(df_now: pd.DataFrame, df_prev: pd.DataFrame) -> pd.DataFrame:
    """
    【P2-D优化】计算当前时刻的涨跌统计以及与前一分钟相比的涨跌统计
    
    根据USE_OPTIMIZED_STATS开关，自动选择优化版或原版实现。
    优化版使用value_counts替代多次遍历，性能提升2-3x，结果100%一致。
    
    Args:
        df_now (pd.DataFrame): 当前时刻的数据，必须包含 'time'、code 和 change_pct 列。
        df_prev (pd.DataFrame): 前一分钟的数据，必须包含 code 和 change_pct 列（可为空）。

    Returns:
        pd.DataFrame: 单行宽表，包含当前统计、分钟统计和 time 字段。
                      各统计字段说明见代码内部。

    Raises:
        ValueError: 如果必要列缺失或 df_prev 非空但缺少必要列。
    """
    # 【P2-D】根据开关选择实现
    if USE_OPTIMIZED_STATS:
        return get_market_stats_v2(df_now, df_prev)
    
    # 原实现（保留作为fallback）
    # ---------- 0. 提取时间 ----------
    if 'time' not in df_now.columns:
        raise ValueError("df_now 必须包含 'time' 列")
    time_value = df_now['time'].iloc[0]

    # ---------- 1. 确保 change_pct 列为数值类型 ----------
    required_cols = ['code', 'change_pct']
    if not all(col in df_now.columns for col in required_cols):
        # 【P2-B】尝试使用stock_code作为code的别名
        if 'stock_code' in df_now.columns and 'code' not in df_now.columns:
            df_now['code'] = df_now['stock_code']
        if not all(col in df_now.columns for col in required_cols):
            raise ValueError(f"df_now 必须包含 'code' 和 'change_pct' 列")

    # 【P2-B优化】数据已在deal_gp_works中统一清洗，change_pct已经是数值
    # 只需要dropna处理NaN值
    df_now = df_now.dropna(subset=['change_pct'])

    # 对 df_prev 做相同处理（如果存在且非空）
    if df_prev is not None and not df_prev.empty:
        if not all(col in df_prev.columns for col in required_cols):
            # 【P2-B】尝试使用stock_code作为code的别名
            if 'stock_code' in df_prev.columns and 'code' not in df_prev.columns:
                df_prev['code'] = df_prev['stock_code']
            if not all(col in df_prev.columns for col in required_cols):
                raise ValueError(f"df_prev 必须包含 'code' 和 'change_pct' 列")
        df_prev['change_pct'] = pd.to_numeric(df_prev['change_pct'], errors='coerce')
        df_prev = df_prev.dropna(subset=['change_pct'])

    # ---------- 2. 当前统计 ----------
    total_cur = len(df_now)
    if total_cur == 0:
        cur_up = cur_down = cur_flat = 0
        cur_up_ratio = cur_down_ratio = cur_flat_ratio = 0.0
        cur_up_down_ratio = np.nan
    else:
        cur_up = (df_now['change_pct'] > 0).sum()
        cur_down = (df_now['change_pct'] < 0).sum()
        cur_flat = (df_now['change_pct'].eq(0)).sum()
        cur_up_ratio = round(cur_up / total_cur * 100, 2)
        cur_down_ratio = round(cur_down / total_cur * 100, 2)
        cur_flat_ratio = round(cur_flat / total_cur * 100, 2)
        if cur_down == 0:
            cur_up_down_ratio = None
        else:
            cur_up_down_ratio = round(cur_up / cur_down * 100, 2)

    # ---------- 3. 分钟统计 ----------
    if df_prev is None or df_prev.empty:
        min_up = min_down = min_flat = min_total = 0
        min_up_ratio = min_down_ratio = min_flat_ratio = 0.0
        min_up_down_ratio = np.nan
    else:
        # 统一 stock_code 为字符串类型（避免合并时类型冲突）
        df_now['code'] = df_now['code'].astype(str)
        if df_prev is not None and not df_prev.empty:
            df_prev['code'] = df_prev['code'].astype(str)

        # 然后进行合并
        merged = pd.merge(
            df_now[['code', 'change_pct']],
            df_prev[['code', 'change_pct']],
            on='code',
            suffixes=('_cur', '_prev'),
            how='inner'
        )

        min_total = len(merged)
        if min_total == 0:
            min_up = min_down = min_flat = 0
            min_up_ratio = min_down_ratio = min_flat_ratio = 0.0
            min_up_down_ratio = np.nan
        else:
            diff = merged['change_pct_cur'] - merged['change_pct_prev']
            min_up = (diff > 0).sum()
            min_down = (diff < 0).sum()
            min_flat = (diff.eq(0)).sum()
            min_up_ratio = round(min_up / min_total * 100, 2)
            min_down_ratio = round(min_down / min_total * 100, 2)
            min_flat_ratio = round(min_flat / min_total * 100, 2)
            if min_down == 0:
                min_up_down_ratio = None
            else:
                min_up_down_ratio = round(min_up / min_down * 100, 2)

    # ---------- 4. 合并为宽表（包含 time）----------
    result = pd.DataFrame([{
        'time': time_value,
        'cur_up': cur_up,
        'cur_down': cur_down,
        'cur_flat': cur_flat,
        'cur_total': total_cur,
        'cur_up_ratio': cur_up_ratio,
        'cur_down_ratio': cur_down_ratio,
        'cur_flat_ratio': cur_flat_ratio,
        'cur_up_down_ratio': cur_up_down_ratio,
        'min_up': min_up,
        'min_down': min_down,
        'min_flat': min_flat,
        'min_total': min_total,
        'min_up_ratio': min_up_ratio,
        'min_down_ratio': min_down_ratio,
        'min_flat_ratio': min_flat_ratio,
        'min_up_down_ratio': min_up_down_ratio
    }])

    # ---------- 5. 强制将比率列转换为 float（避免后续字符串比较错误）----------
    ratio_cols = [
        'cur_up_ratio', 'cur_down_ratio', 'cur_flat_ratio', 'cur_up_down_ratio',
        'min_up_ratio', 'min_down_ratio', 'min_flat_ratio', 'min_up_down_ratio'
    ]
    result[ratio_cols] = result[ratio_cols].astype(float)

    return result


# ------------------------------
# P2-D: 大盘统计优化开关
# ------------------------------
USE_OPTIMIZED_STATS = True


def get_market_stats_v2(df_now: pd.DataFrame, df_prev: pd.DataFrame) -> pd.DataFrame:
    """
    【P2-D优化】计算当前时刻的涨跌统计以及与前一分钟相比的涨跌统计
    
    优化点（方案A - 保持100%一致）：
    1. 删除重复类型转换（P2-B后数据已清洗）
    2. 使用value_counts一次遍历统计（保持dropna与原方案一致）
    3. 使用set_index替代merge，减少内存拷贝
    4. 预计算结果，减少中间变量
    
    Args:
        df_now: 当前时刻数据（已清洗）
        df_prev: 前一分钟数据（已清洗）
    
    Returns:
        pd.DataFrame: 单行宽表，包含当前统计和分钟统计
    """
    # ---------- 0. 提取时间 ----------
    time_value = df_now['time'].iloc[0] if 'time' in df_now.columns else ''
    
    # 【P2-B】数据已清洗，直接使用
    # 只需要确保code列存在
    if 'code' not in df_now.columns and 'stock_code' in df_now.columns:
        df_now = df_now.copy()
        df_now['code'] = df_now['stock_code']
    
    # 【方案A】保持与原方案一致：先dropna
    df_now = df_now.dropna(subset=['change_pct'])
    total_cur = len(df_now)
    
    # ---------- 1. 当前统计（向量化一次遍历） ----------
    if total_cur == 0:
        cur_stats = {'up': 0, 'down': 0, 'flat': 0}
        cur_ratios = {'up': 0.0, 'down': 0.0, 'flat': 0.0, 'up_down': np.nan}
    else:
        # 【优化】使用value_counts一次统计（此时已无NaN）
        change_sign = np.sign(df_now['change_pct'])
        counts = change_sign.value_counts().to_dict()
        
        cur_stats = {
            'up': int(counts.get(1.0, 0)),
            'down': int(counts.get(-1.0, 0)),
            'flat': int(counts.get(0.0, 0))
        }
        
        # 【优化】预计算比率
        cur_ratios = {
            'up': round(cur_stats['up'] / total_cur * 100, 2),
            'down': round(cur_stats['down'] / total_cur * 100, 2),
            'flat': round(cur_stats['flat'] / total_cur * 100, 2),
            'up_down': round(cur_stats['up'] / cur_stats['down'] * 100, 2) 
                       if cur_stats['down'] > 0 else np.nan
        }
    
    # ---------- 2. 分钟统计（简化merge） ----------
    if df_prev is None or df_prev.empty:
        min_stats = {'up': 0, 'down': 0, 'flat': 0, 'total': 0}
        min_ratios = {'up': 0.0, 'down': 0.0, 'flat': 0.0, 'up_down': np.nan}
    else:
        # 【优化】使用set_index替代merge
        if 'code' not in df_prev.columns and 'stock_code' in df_prev.columns:
            df_prev = df_prev.copy()
            df_prev['code'] = df_prev['stock_code']
        
        # 【方案A】保持与原方案一致：先dropna
        df_prev = df_prev.dropna(subset=['change_pct'])
        
        # 【优化】set_index + reindex替代merge
        prev_indexed = df_prev.set_index('code')['change_pct']
        now_codes = df_now['code'].unique()
        prev_matched = prev_indexed.reindex(now_codes)
        
        # 计算变化
        now_indexed = df_now.set_index('code')['change_pct']
        diff = now_indexed - prev_matched
        diff = diff.dropna()  # 删除前时刻不存在的
        
        min_total = len(diff)
        
        if min_total == 0:
            min_stats = {'up': 0, 'down': 0, 'flat': 0, 'total': 0}
            min_ratios = {'up': 0.0, 'down': 0.0, 'flat': 0.0, 'up_down': np.nan}
        else:
            # 【优化】value_counts一次统计
            diff_sign = np.sign(diff)
            min_counts = diff_sign.value_counts().to_dict()
            
            min_stats = {
                'up': int(min_counts.get(1.0, 0)),
                'down': int(min_counts.get(-1.0, 0)),
                'flat': int(min_counts.get(0.0, 0)),
                'total': min_total
            }
            
            min_ratios = {
                'up': round(min_stats['up'] / min_total * 100, 2),
                'down': round(min_stats['down'] / min_total * 100, 2),
                'flat': round(min_stats['flat'] / min_total * 100, 2),
                'up_down': round(min_stats['up'] / min_stats['down'] * 100, 2)
                           if min_stats['down'] > 0 else np.nan
            }
    
    # ---------- 3. 构建结果（预计算，无重复转换） ----------
    result = pd.DataFrame([{
        'time': time_value,
        'cur_up': cur_stats['up'],
        'cur_down': cur_stats['down'],
        'cur_flat': cur_stats['flat'],
        'cur_total': total_cur,
        'cur_up_ratio': cur_ratios['up'],
        'cur_down_ratio': cur_ratios['down'],
        'cur_flat_ratio': cur_ratios['flat'],
        'cur_up_down_ratio': cur_ratios['up_down'],
        'min_up': min_stats['up'],
        'min_down': min_stats['down'],
        'min_flat': min_stats['flat'],
        'min_total': min_stats['total'],
        'min_up_ratio': min_ratios['up'],
        'min_down_ratio': min_ratios['down'],
        'min_flat_ratio': min_ratios['flat'],
        'min_up_down_ratio': min_ratios['up_down']
    }])
    
    # 【方案A】保持与原方案一致：比率列转为float
    ratio_cols = [
        'cur_up_ratio', 'cur_down_ratio', 'cur_flat_ratio', 'cur_up_down_ratio',
        'min_up_ratio', 'min_down_ratio', 'min_flat_ratio', 'min_up_down_ratio'
    ]
    result[ratio_cols] = result[ratio_cols].astype(float)
    
    return result


def judge_market_strength(stats_row):
    """
    基于 get_market_stats 返回的一行数据，多维度判断市场强弱及转换信号。
    返回结果为单行宽表，包含原始统计字段及新增的判断字段。

    Args:
        stats_row (pd.Series 或 pd.DataFrame): get_market_stats 返回的一行数据，
                                                如果是 DataFrame 必须只有一行。

    Returns:
        pd.DataFrame: 单行宽表，包含原始统计字段以及新增的：
                      strength_score, state, signal, base_score, trend_score。

    Raises:
        ValueError: 如果 stats_row 包含多行数据。
    """
    # 确保输入为 Series
    if isinstance(stats_row, pd.DataFrame):
        if len(stats_row) > 1:
            raise ValueError("stats_row 只能包含一行数据，请使用 .iloc[0] 传入 Series")
        stats_row = stats_row.iloc[0]

    # ---------- 强制转换为浮点数（避免字符串与数字比较错误）----------
    # 将需要用到的指标全部转为 float（np.inf / np.nan 也能正确处理）
    cur_up_ratio = float(stats_row['cur_up_ratio'])
    cur_down_ratio = float(stats_row['cur_down_ratio'])
    cur_up_down_ratio = float(stats_row['cur_up_down_ratio'])
    min_up_ratio = float(stats_row['min_up_ratio'])
    min_down_ratio = float(stats_row['min_down_ratio'])
    min_up_down_ratio = float(stats_row['min_up_down_ratio'])
    min_up = float(stats_row['min_up'])
    min_down = float(stats_row['min_down'])
    cur_total = float(stats_row['cur_total'])

    # --- 1. 当前强度基础评分（0-100）---
    base_score = cur_up_ratio

    # 涨跌比修正
    if not pd.isna(cur_up_down_ratio) and cur_up_down_ratio is not None:
        if cur_up_down_ratio > 200:
            base_score += min(cur_up_down_ratio - 200, 200) * 0.1
        elif cur_up_down_ratio < 50:
            base_score -= (50 - cur_up_down_ratio) * 0.2
    elif cur_up_down_ratio is None:
        base_score += 20

    base_score = max(0.0, min(100.0, base_score))

    # --- 2. 趋势修正（基于分钟变化）---
    trend_score = (min_up_ratio - 50) * 0.8
    trend_score = max(-20.0, min(20.0, trend_score))

    strength_score = base_score + trend_score
    strength_score = max(0.0, min(100.0, strength_score))

    # --- 3. 市场状态划分 ---
    if strength_score >= 80:
        state = "极强"
    elif strength_score >= 60:
        state = "强"
    elif strength_score <= 20:
        state = "极弱"
    elif strength_score <= 40:
        state = "弱"
    else:
        state = "温和"

    # --- 4. 转换信号识别 ---
    signal = "无"
    if cur_up_ratio <= 40 and min_up_ratio > 55 and min_up > min_down:
        signal = "弱转强"
    elif cur_up_ratio >= 60 and min_down_ratio > 55 and min_down > min_up:
        signal = "强转弱"
    else:
        if cur_up_ratio <= 40 and not pd.isna(min_up_down_ratio) and min_up_down_ratio > 200:
            signal = "弱转强（潜在）"
        elif cur_up_ratio >= 60 and not pd.isna(min_up_down_ratio) and min_up_down_ratio < 50:
            signal = "强转弱（潜在）"

    # --- 5. 构造结果 DataFrame：合并原始统计字段与新增字段 ---
    original_dict = stats_row.to_dict()
    original_dict.update({
        'strength_score': round(strength_score, 2),
        'state': state,
        'signal': signal,
        'base_score': round(base_score, 2),
        'trend_score': round(trend_score, 2)
    })
    result_df = pd.DataFrame([original_dict])
    return result_df
# 源字段
SOURCE_STOCK_FULL_COLUMNS = ['stock_code', 'short_name', 'price','change','change_pct', 'volume', 'amount']
# 统一后字段 'code', 'name', 'price','change','change_pct', 'volume', 'amount'

def deal_gp_works(loop_start):
    """
    单个轮询周期的主处理函数：获取股票数据、存储实时数据、计算前30秒指标及大盘强度。

    Args:
        loop_start (datetime): 当前轮询开始时间。
    """
    # 添加时间字段（HH:MM:SS）
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")

    try:
        df_now = fetch_all_concurrently(STOCK_CODES)
        if df_now.empty:
            # 数据为空，创建占位空DataFrame（包含后续计算所需的全部列）
            df_now = pd.DataFrame(columns=SOURCE_STOCK_FULL_COLUMNS)
        else:
            # 【P2-B优化】统一数据清洗
            if USE_UNIFIED_CLEAN:
                df_now = normalize_stock_dataframe(df_now, required_cols=['stock_code', 'price'])
                logger.info(f"[{time_full}] 数据清洗完成: {len(df_now)}只有效")
            else:
                # 兼容旧逻辑
                df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)
    except Exception as e:
        logger.error(f"获取股票数据异常: {e}")
        df_now = pd.DataFrame(columns=SOURCE_STOCK_FULL_COLUMNS)

    df_now['time'] = time_full

    # ========== 新增：计算涨停字段 ==========
    if not df_now.empty:
        # 转换 change_pct 为数值
        df_now['change_pct'] = pd.to_numeric(df_now['change_pct'], errors='coerce')
        
        # 计算是否涨停
        if USE_VECTORIZED:
            df_now['is_zt'] = calc_is_zt_vectorized(df_now)
        else:
            df_now['is_zt'] = df_now.apply(
                lambda row: calc_is_zt(
                    row.get('change_pct'), 
                    row.get('stock_code', ''),
                    row.get('short_name', '')
                ), 
                axis=1
            )
        
        # 更新曾经涨停缓存
        zt_codes = set(df_now[df_now['is_zt'] == 1]['stock_code'].tolist())
        update_ever_zt_cache(date_str, zt_codes)
        
        # 计算是否曾经涨停
        df_now['ever_zt'] = df_now['stock_code'].apply(
            lambda code: is_ever_zt(code, date_str)
        )
        
        logger.info(f"涨停统计: 当前涨停 {df_now['is_zt'].sum()} 只, "
                   f"曾经涨停 {df_now['ever_zt'].sum()} 只")

    # 添加集合竞价标记
    is_auction, auction_period = is_in_auction_period(loop_start.time())
    df_now['is_auction'] = is_auction
    df_now['auction_period'] = auction_period if is_auction else None

    # ========== 新增：计算主力净额 ==========
    # 获取当日统计数据（用于计算价格位置）
    day_stats = get_day_stats(df_now)
    
    # 计算主力净额（需要上一时刻数据，在获取df_prev后计算）
    main_force_result = None
    
    # 【修改】先不保存，等计算完主力净额和累计值后再保存
    sssj_table = f"monitor_gp_sssj_{date_str}"

    # 【新增】自动添加索引（仅在第一次写入时）
    try:
        add_index_on_first_write(sssj_table, time_full)
    except Exception as e:
        logger.warning(f"添加索引失败（非关键错误）: {e}")

    # 获取前30秒的数据（从 Redis 加载）
    # 集合竞价期间不计算前30秒数据（因为没有连续数据）
    time_obj = loop_start.time()
    is_early_morning = (dt_time(9, 30, 0) <= time_obj < dt_time(9, 30, 15))
    
    if is_auction:
        df_prev = None
        logger.info(f"[集合竞价] {time_full} 跳过前30秒数据计算")
    elif is_early_morning:
        # 早盘9:30:00-9:30:15：获取最早时间戳作为基准
        earliest_time = redis_util.get_earliest_timestamp(sssj_table)
        if earliest_time:
            df_prev = redis_util.load_dataframe_by_key(f"{sssj_table}:{earliest_time}", use_compression=False)
            logger.info(f"[早盘] {time_full} 使用最早数据({earliest_time})作为基准，共{len(df_prev) if df_prev is not None else 0}条")
        else:
            logger.warning(f"[早盘] {time_full} 无法获取最早时间戳，跳过计算")
            df_prev = None
    else:
        window_seconds_offset = (WINDOW_SECONDS + INTERVAL - 1) // INTERVAL
        df_prev = redis_util.load_dataframe_by_offset(sssj_table, offset=window_seconds_offset, use_compression=False)

    # ========== 【修改】严格区分 df_prev 和 df_prev_main ==========
    
    # 【不变】df_prev 用于上攻排行计算（15秒周期）
    # df_prev 已在上面的代码中获取
    
    # 【新增】df_prev_main 用于主力净额计算（时间戳查询）
    df_prev_main = None
    if not is_auction:
        try:
            # 找上一个有数据的时间点（非15秒周期）
            prev_time = redis_util.get_prev_timestamp_with_data(sssj_table, time_full)
            if prev_time:
                df_prev_main = redis_util.load_dataframe_by_time(sssj_table, prev_time)
                logger.info(f"[{time_full}] 主力净额计算使用时间点: {prev_time}")
        except Exception as e:
            logger.warning(f"[{time_full}] 获取上一时间点失败: {e}")
    
    # ========== 【修改】计算主力净额和累计值 ==========
    if not is_auction and df_prev_main is not None and not df_prev_main.empty:
        try:
            # 【修改】使用一体化计算函数，直接使用df_prev_main
            df_now = calculate_main_force_and_cumulative(
                df_now, df_prev_main, day_stats, loop_start.time()
            )
            
            non_zero_main = (df_now['main_net_amount'] != 0).sum()
            non_zero_cum = (df_now['cumulative_main_net'] != 0).sum()
            logger.info(f"[{time_full}] 主力净额计算完成: main={non_zero_main}, cum={non_zero_cum}")
            
        except Exception as e:
            logger.error(f"[{time_full}] 主力净额计算失败: {e}")
            # 添加空字段
            df_now['main_net_amount'] = 0.0
            df_now['main_behavior'] = '无主力'
            df_now['main_confidence'] = 0.0
            df_now['cumulative_main_net'] = 0.0
    else:
        # 集合竞价或无上一时刻数据
        df_now['main_net_amount'] = 0.0
        df_now['main_behavior'] = '无主力'
        df_now['main_confidence'] = 0.0
        df_now['cumulative_main_net'] = 0.0
        if is_auction:
            logger.info(f"[{time_full}] 集合竞价，主力净额置0")
        else:
            logger.warning(f"[{time_full}] 无上一时刻数据，主力净额置0")
    
    # 【P1-B优化】异步保存包含主力净额和累计值的数据
    try:
        save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)
        logger.info(f"[{time_full}] 已提交异步保存实时数据，共 {len(df_now)} 条")
    except Exception as e:
        logger.error(f"[{time_full}] 保存实时数据失败: {e}")

    # 计算并存储大盘强度
    culculate_gp_apqd_top30(df_now, df_prev, date_str, time_full, loop_start, is_auction, is_early_morning)


def culculate_gp_apqd_top30(df_now, df_prev, date_str, time_full, loop_start, is_auction=False, is_early_morning=False):
    """
    计算大盘强度（APQD）和涨幅/涨速前30榜单，并存储。

    Args:
        df_now (pd.DataFrame): 当前时刻数据。
        df_prev (pd.DataFrame): 30秒前数据（可能为空）。
        date_str (str): 日期字符串 YYYYMMDD。
        time_full (str): 时间字符串 HH:MM:SS。
        loop_start (datetime): 轮询开始时间。
        is_auction (bool): 是否为集合竞价时段。
        is_early_morning (bool): 是否为早盘9:30:00-9:30:15时段。
    """
    # ---------- 列名标准化：将原始列名映射为统一名称 ----------
    rename_map = {}
    if 'stock_code' in df_now.columns and 'code' not in df_now.columns:
        rename_map['stock_code'] = 'code'
    if 'short_name' in df_now.columns and 'name' not in df_now.columns:
        rename_map['short_name'] = 'name'
    if rename_map:
        df_now = df_now.rename(columns=rename_map)
        if df_prev is not None and not df_prev.empty:
            df_prev = df_prev.rename(columns=rename_map)

    # ---------- 确保必要列存在 ----------
    required_cols = ['code', 'change_pct']
    if not all(col in df_now.columns for col in required_cols):
        raise ValueError(f"df_now 缺少必要列 {required_cols}，当前列：{df_now.columns.tolist()}")

    # ---------- 计算大盘强度 ----------
    # 集合竞价期间也计算大盘强度（但可能不准确）
    judge30 = judge_market_strength(get_market_stats(df_now, df_prev))
    apqd_table = f"monitor_gp_apqd_{date_str}"
    save_dataframe_async(judge30, apqd_table, time_full, EXPIRE_SECONDS)

    # ---------- 计算前30榜单 ----------
    # 集合竞价期间不计算前30榜单（因为没有前30秒数据）
    if is_auction:
        logger.info(f"[集合竞价] {time_full} 跳过前30榜单计算")
    elif df_prev is not None and not df_prev.empty:
        top30_df = calculate_top30_v3(df_now, df_prev, loop_start)
        if not top30_df.empty:
            gp_top30_table = f"monitor_gp_top30_{date_str}"
            result_df = attack_conditions(top30_df, rank_name='stock')
            save_dataframe_async(result_df, gp_top30_table, time_full, EXPIRE_SECONDS)
            # 上攻排行 - 顶级游资+超级短线量化思路
            rank_result = redis_util.update_rank_redis(result_df, 'stock', date_str=date_str)
            # 【新增】早盘标记
            if is_early_morning:
                logger.info(f"[早盘] {time_full} 完成上攻排行计算（使用最早时间基准）")
            # 收盘时保存到 MySQL
            if time_full == "15:00:00":
                save_rank_to_mysql(rank_result, 'stock', date_str)
            industry_attack(top30_df, df_now, date_str, time_full)

def industry_attack(top30_df: pd.DataFrame, df_now: pd.DataFrame, 
                    date_str: str, time_full: str):
    """
    行业上攻数据存储
    
    Args:
        top30_df: 上涨股票数据（用于统计上涨数量）
        df_now: 当前时间点所有股票数据（用于计算行业平均涨跌幅）
        date_str: 日期
        time_full: 时间
    """
    hy_top5_df = calculate_industry_topn(top30_df, df_now, date_str, time_full)
    if not hy_top5_df.empty:
        hy_top5_table = f"monitor_hy_top30_{date_str}"
        save_dataframe_async(hy_top5_df, hy_top5_table, time_full, EXPIRE_SECONDS)
        # 上攻排行 - 顶级游资+超级短线量化思路
        hy_rank_result = redis_util.update_rank_redis(hy_top5_df, 'industry', date_str=date_str)
        # 收盘时保存到 MySQL
        if time_full == "15:00:00":
            save_rank_to_mysql(hy_rank_result, 'industry', date_str)

def calculate_industry_topn(
        stock_df: pd.DataFrame,      # 上涨股票（用于统计上涨数量）
        all_stock_df: pd.DataFrame,  # 所有股票（用于计算行业平均涨跌幅和均价）
        date_str: str,
        time_full: str,
        min_industry_return: float = 0,          # 行业最小平均涨跌幅（百分比）
        price_half_life: float = DEFAULT_PRICE_HALF_LIFE,  # 价格半衰期参数K
        price_weight: float = DEFAULT_PRICE_WEIGHT         # 价格因子权重指数α
) -> pd.DataFrame:
    """
    计算行业排行 TOP5（含价格质量因子）

    评分公式：
        final_score = smooth_ratio × confidence × price_quality^α
    
    其中：
        smooth_ratio  = (上涨数 + 2) / (总数 + 20)         — 贝叶斯平滑
        confidence    = f(total)                             — 样本量置信度
        price_quality = 0.5 + 0.5 × (1 - exp(-avg_price/K)) — 价格质量因子
        α = price_weight                                     — 价格因子权重指数
    
    设置 price_weight=0 可关闭价格因子（退化为原始公式）。

    Args:
        stock_df: 上涨股票 DataFrame（用于统计上涨数量）
        all_stock_df: 当前时间点所有股票 DataFrame（含 price 列，用于计算均价和平均涨跌幅）
        date_str: 日期字符串 YYYYMMDD
        time_full: 时间字符串 HH:MM:SS
        min_industry_return: 行业最小平均涨跌幅，低于此值被过滤（默认0%）
        price_half_life: 价格质量因子半衰期K（默认15.0，均价K元时quality≈0.82）
        price_weight: 价格因子权重指数α（默认0.5，0=关闭）

    Returns:
        行业排行 TOP5 DataFrame，包含字段：
        code, name, count, total, avg_change_pct, avg_price, price_quality,
        raw_ratio, smooth_ratio, confidence, final_score, rank, rq, time
    """
    empty_result = pd.DataFrame(columns=INDUSTRY_RESULT_COLUMNS)

    if stock_df is None or stock_df.empty or all_stock_df is None or all_stock_df.empty:
        logger.info(f"[{time_full}] 无数据，跳过行业排行计算")
        return empty_result

    try:
        # ========== 1. 获取行业映射缓存 ==========
        mapping_cache = _ensure_industry_mapping(time_full)
        if not mapping_cache:
            logger.error(f"[{time_full}] 行业映射不可用，无法计算行业排行")
            return empty_result

        # ========== 2. 列名标准化 ==========
        all_df = _normalize_stock_df(all_stock_df)
        up_df = _normalize_stock_df(stock_df)

        if 'code' not in all_df.columns:
            logger.error(f"[{time_full}] all_stock_df 缺少 'code' 列，当前列: {all_df.columns.tolist()}")
            return empty_result

        # ========== 3. 行业映射（扁平字典，高效） ==========
        code_to_industry = {k: v['industry_code'] for k, v in mapping_cache.items()}
        code_to_indname = {k: v['industry_name'] for k, v in mapping_cache.items()}

        all_df['industry_code'] = all_df['code'].map(code_to_industry).fillna('')
        all_df['industry_name'] = all_df['code'].map(code_to_indname).fillna('')

        mapped_count = (all_df['industry_code'] != '').sum()
        logger.info(f"[{time_full}] 行业映射: {mapped_count}/{len(all_df)} 只股票")

        # 过滤有效数据
        valid_df = all_df[all_df['industry_code'].ne('') & all_df['industry_code'].notna()]
        if valid_df.empty:
            logger.warning(f"[{time_full}] 无有效行业映射")
            return empty_result

        # ========== 4. 向量化计算行业统计（单次groupby） ==========
        if 'change_pct' not in valid_df.columns:
            logger.error(f"[{time_full}] 缺少涨跌幅列，当前列: {valid_df.columns.tolist()}")
            return empty_result

        # 确保 price 列存在且为数值
        has_price = 'price' in valid_df.columns
        if has_price:
            valid_df = valid_df.copy()
            valid_df['price'] = pd.to_numeric(valid_df['price'], errors='coerce')

        # 聚合：平均涨跌幅、股票总数、平均价格
        agg_dict = {
            'change_pct': 'mean',
            'code': 'count'
        }
        if has_price:
            agg_dict['price'] = 'mean'

        industry_stats = valid_df.groupby(['industry_code', 'industry_name']).agg(agg_dict).reset_index()

        # 重命名列
        rename_map = {'change_pct': 'avg_change_pct', 'code': 'total'}
        if has_price:
            rename_map['price'] = 'avg_price'
        industry_stats = industry_stats.rename(columns=rename_map)

        # 若无 price 列，填充默认值（不影响评分，quality=1.0）
        if 'avg_price' not in industry_stats.columns:
            industry_stats['avg_price'] = 0.0

        # ========== 5. 向量化计算上涨数量 ==========
        up_df['industry_code'] = up_df['code'].map(code_to_industry).fillna('')
        up_counts = up_df[up_df['industry_code'].isin(industry_stats['industry_code'])] \
            .groupby('industry_code').size()

        industry_stats = industry_stats.set_index('industry_code')
        industry_stats['count'] = up_counts.reindex(industry_stats.index).fillna(0).astype(int)
        industry_stats = industry_stats.reset_index()

        # 过滤无上涨的行业
        industry_stats = industry_stats[industry_stats['count'] > 0]
        if industry_stats.empty:
            logger.info(f"[{time_full}] 无行业上涨数据")
            return empty_result

        # ========== 6. 过滤表现差的行业 ==========
        good_mask = industry_stats['avg_change_pct'] > min_industry_return
        good = industry_stats[good_mask].copy()

        filtered_count = (~good_mask).sum()
        if filtered_count > 0:
            logger.info(f"[{time_full}] 过滤 {filtered_count} 个表现差的行业（平均涨幅 < {min_industry_return}%）")

        if good.empty:
            logger.info(f"[{time_full}] 无有效行业数据（整体表现差）")
            return empty_result

        # ========== 7. 贝叶斯平滑 + 置信度 + 价格质量因子 ==========
        PRIOR_UP, PRIOR_TOTAL = 2, 20
        good['raw_ratio'] = good['count'] / good['total']
        good['smooth_ratio'] = (good['count'] + PRIOR_UP) / (good['total'] + PRIOR_TOTAL)

        # 置信度（向量化）
        def calc_confidence_vectorized(total_series):
            result = pd.Series(index=total_series.index, dtype=float)
            mask_s = total_series < 20
            mask_m = (total_series >= 20) & (total_series < 100)
            mask_l = total_series >= 100
            result[mask_s] = 0.6 + 0.2 * total_series[mask_s] / 20
            result[mask_m] = 0.8 + 0.15 * (total_series[mask_m] - 20) / 80
            result[mask_l] = np.minimum(1.0, 0.95 + 0.05 * (total_series[mask_l] - 100) / 100)
            return result

        good['confidence'] = calc_confidence_vectorized(good['total'])

        # 价格质量因子
        good['price_quality'] = _calc_price_quality(good['avg_price'], K=price_half_life)

        # 最终评分：smooth_ratio × confidence × price_quality^α
        if price_weight > 0:
            good['final_score'] = good['smooth_ratio'] * good['confidence'] * (good['price_quality'] ** price_weight)
        else:
            # α=0 时关闭价格因子，退化为原始公式
            good['final_score'] = good['smooth_ratio'] * good['confidence']

        # ========== 8. 排序取TOP5，向量化构建结果 ==========
        top5 = good.nlargest(5, 'final_score').reset_index(drop=True)
        top5['rank'] = range(1, len(top5) + 1)
        top5['rq'] = date_str
        top5['time'] = time_full

        # 列重命名 + 选择
        result_df = top5.rename(columns={'industry_code': 'code', 'industry_name': 'name'})

        # 确保所有结果列存在
        for col in INDUSTRY_RESULT_COLUMNS:
            if col not in result_df.columns:
                result_df[col] = 0

        result_df = result_df[INDUSTRY_RESULT_COLUMNS]

        # 数值精度
        for col in ['avg_change_pct', 'avg_price', 'price_quality',
                     'raw_ratio', 'smooth_ratio', 'confidence', 'final_score']:
            result_df[col] = result_df[col].round(4)
        result_df['count'] = result_df['count'].astype(int)
        result_df['total'] = result_df['total'].astype(int)

        # 日志输出
        logger.info(f"[{time_full}] 行业排行 TOP5:")
        for _, row in result_df.iterrows():
            logger.info(f"  第{row['rank']}名 {row['name']}: "
                       f"上涨{row['count']}/{row['total']}, "
                       f"均价{row['avg_price']:.1f}元, "
                       f"涨幅{row['avg_change_pct']:.2f}%, "
                       f"质量{row['price_quality']:.3f}, "
                       f"得分{row['final_score']:.4f}")

        return result_df

    except Exception as e:
        logger.error(f"[{time_full}] 计算行业排行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return pd.DataFrame(columns=INDUSTRY_RESULT_COLUMNS)

def attack_conditions(top30_df: pd.DataFrame,rank_name: str = 'default'):
    """
    上攻排行榜条件过滤
    :param top30_df:
    :param rank_name:
    :return:
    """
    if rank_name == 'stock':
        result_df = top30_df[
            (top30_df['amount_rank'] <= 500) &
            (top30_df['zf_30'] >= 0.2) &
            (top30_df['momentum'] >= 50) &
            (top30_df['total_score_rank'] <= 60)
        ]
        return result_df
    elif rank_name == 'bond':
        result_df = top30_df[
            (top30_df['amount_rank'] <= 50) &
            (top30_df['zf_30'] >= 0.2) &
            (top30_df['momentum'] >= 50) &
            (top30_df['total_score_rank'] <= 10)
        ]
        return result_df
    elif rank_name == 'industry':
        return top30_df
    else:
        return top30_df


def save_rank_to_mysql(rank_df: pd.DataFrame, rank_name: str, date_str: str) -> None:
    """
    将排行榜数据保存到 MySQL
    
    Args:
        rank_df: 排行榜 DataFrame（包含 code, name, count, date 列）
        rank_name: 排行榜名称（stock/bond/industry）
        date_str: 日期字符串 YYYYMMDD
    """
    if rank_df is None or rank_df.empty:
        return
    
    try:
        from sqlalchemy import text
        
        table_name = f"rank_{rank_name}"
        
        # 检查表是否存在，不存在则创建
        check_sql = text(f"""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}'
        """)
        result = con.execute(check_sql)
        table_exists = result.scalar() > 0
        
        if not table_exists:
            logger.info(f"表 {table_name} 不存在，自动创建...")
            create_sql = text(f"""
                CREATE TABLE {table_name} (
                    code VARCHAR(20) NOT NULL,
                    name VARCHAR(100),
                    count INT,
                    date VARCHAR(8) NOT NULL,
                    PRIMARY KEY (code, date)
                )
            """)
            con.execute(create_sql)
            con.commit()
            logger.info(f"表 {table_name} 创建成功")
        
        # 先删除该日期的旧数据，避免重复
        delete_sql = text(f"DELETE FROM {table_name} WHERE date = '{date_str}'")
        con.execute(delete_sql)
        con.commit()
        
        # 插入新数据
        rank_df.to_sql(table_name, con=engine, if_exists='append', index=False)
        logger.info(f"已保存 {rank_name} 排行榜到 MySQL 表 {table_name}，日期: {date_str}，共 {len(rank_df)} 条")
    except Exception as e:
        logger.error(f"保存排行榜到 MySQL 失败: {e}")


def run_monitor_loop_synced(process_func, interval=INTERVAL):
    """
    同步监控主循环（优化版）：支持集合竞价时段只获取一次数据
    在 interval 秒的整数倍时刻执行 process_func。
    """
    last_date = None

    while True:
        now = time.time()
        # 计算下一个整数倍时刻
        next_time = ((now + interval) // interval) * interval
        sleep_seconds = next_time - now
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

        target_dt = datetime.fromtimestamp(next_time)
        current_date = target_dt.date()

        # 日期变更时重置集合竞价标志
        if last_date != current_date:
            reset_auction_flags()
            last_date = current_date
            logger.info(f"日期变更，重置集合竞价标志: {current_date}")

        # 检查是否在集合竞价时段
        is_auction, period_name = is_in_auction_period(target_dt.time())

        if is_auction:
            # 集合竞价时段：只获取一次数据
            # 【修复】尾市集合竞价（14:57-15:00）的15:00:00必须采集
            if period_name == 'afternoon' and target_dt.time() == dt_time(15, 0):
                # 15:00:00 必须采集，不跳过
                logger.info(f"[集合竞价] {target_dt.strftime('%H:%M:%S')} 尾市收盘，必须采集")
            elif _auction_data_fetched[period_name]:
                # 已获取过，跳过本次
                logger.info(f"[集合竞价] {target_dt.strftime('%H:%M:%S')} 已获取数据，跳过")
                continue
            else:
                # 首次获取，设置标志
                _auction_data_fetched[period_name] = True
                logger.info(f"[集合竞价] {target_dt.strftime('%H:%M:%S')} 首次获取数据")

        if not is_trading_time(target_dt):
            if is_past_1500(target_dt):
                print(f"当前时间 {target_dt} 已过15:00，程序退出")
                redis_util.close_redis()
                sys.exit(0)
            next_start = next_trading_start(target_dt)
            sleep_until = (next_start - datetime.now()).total_seconds()
            if sleep_until > 0:
                print(f"当前不在交易时间，休眠 {sleep_until:.2f} 秒直到 {next_start.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(sleep_until)
            continue

        # print(f"开始获取数据... {target_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        process_func(target_dt)

        if is_past_1500(datetime.now()):
            print("已过15:00，程序退出")
            redis_util.close_redis()
            sys.exit(0)


if __name__ == "__main__":
    run_monitor_loop_synced(deal_gp_works, interval=INTERVAL)