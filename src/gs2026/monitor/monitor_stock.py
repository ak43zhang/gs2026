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
from sqlalchemy import types as sa_types
from sqlalchemy.exc import SAWarning

from gs2026.utils import log_util, pandas_display_config,config_util,mysql_util,redis_util,string_enum
from gs2026.monitor.table_index_manager import add_index_on_first_write, auto_add_index
from gs2026.monitor.monitor_derived_fields import calculate_all_derived

# ========== 区间次数缓存导入（可删除块开始）==========
# 新方案：纯内存缓存 + 数据库宕机恢复
_tick_window_cache = {}  # {(date, window_start, code): count}
_last_wc_window_start = None  # 上一次的区间起始（用于跨区间检测）

def _calculate_window_start(time_str: str) -> str:
    """计算15分钟区间起始"""
    hh, mm, _ = time_str.split(':')
    hour, minute = int(hh), int(mm)
    return f"{hour:02d}:{(minute // 15) * 15:02d}:00"

def _batch_recover_window_counts(codes: list, date: str, time_str: str,
                                  table_name: str, engine) -> dict:
    """批量恢复多个票的区间次数（宕机恢复用）"""
    global _tick_window_cache
    
    window_start = _calculate_window_start(time_str)
    
    # 筛选需要恢复的票（不在内存缓存中的）
    codes_to_recover = []
    for code in codes:
        key = (date, window_start, code)
        if key not in _tick_window_cache:
            codes_to_recover.append(code)
    
    if not codes_to_recover:
        # 全部在缓存中，直接返回当前值
        return {code: _tick_window_cache.get((date, window_start, code), 0) 
                for code in codes}
    
    # 批量查询数据库
    try:
        from sqlalchemy import text
        codes_str = "','".join(codes_to_recover)
        sql = f"""
            SELECT code, COUNT(*) as cnt 
            FROM {table_name}
            WHERE code IN ('{codes_str}')
            AND time >= '{window_start}' 
            AND time < '{time_str}'
            GROUP BY code
        """
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            db_counts = {row[0]: row[1] for row in result}
    except Exception as e:
        logger.warning(f"批量恢复window_count失败: {e}")
        db_counts = {}
    
    # 更新内存缓存（数据库计数作为当前值）
    for code in codes_to_recover:
        key = (date, window_start, code)
        _tick_window_cache[key] = db_counts.get(code, 0)
    
    return {code: _tick_window_cache[(date, window_start, code)] for code in codes}

# 保留旧导入兼容（可删除块结束）
try:
    from gs2026.monitor.window_count_cache import get_window_count
    _window_count_enabled = True
except ImportError:
    _window_count_enabled = False
    def get_window_count(*args, **kwargs):
        return 0

# ========== 向量化优化导入 ==========
try:
    from gs2026.monitor.vectorized_funcs import (
        calculate_participation_ratio_vectorized
    )
    USE_VECTORIZED = True
except ImportError:
    USE_VECTORIZED = False

# 涨停规则模块（新增，统一管理涨停判断）
from gs2026.monitor.module.zt_limit import (
    get_zt_limit,
    is_zt,
    is_dt,
    get_zt_limit_vectorized,
    calc_is_zt_vectorized
)

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url = config_util.get_config("common.url")
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')

# 【修复】添加 charset=utf8mb4 支持 emoji
# 替换 utf8 为 utf8mb4
url = url.replace('charset=utf8', 'charset=utf8mb4')
if 'charset=utf8mb4' not in url:
    if '?' in url:
        url += '&charset=utf8mb4'
    else:
        url += '?charset=utf8mb4'

engine = config_util.get_engine(pool_size=20, max_overflow=30)
# 注意：不要创建全局连接，使用 with engine.connect() 上下文管理器

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
    3. 【修复】标记无效数据（price/volume/amount <= 0），但不删除
    4. 填充默认值（main_net_amount/cumulative_main_net缺失时填0）
    5. 删除重复代码（保留第一个）

    Args:
        df: 原始DataFrame
        required_cols: 必需列列表，缺失时返回空DataFrame

    Returns:
        pd.DataFrame: 清洗后的DataFrame，包含is_invalid标记列
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

    # 4. 【修复】标记无效数据，但不删除，便于后续从前一tick恢复
    if all(c in df.columns for c in ['price', 'volume', 'amount']):
        invalid_mask = (df['price'] <= 0) | (df['volume'] <= 0) | (df['amount'] <= 0)
        # 标记无效数据，保留所有数据用于后续恢复
        df['is_invalid'] = invalid_mask.astype(int)
    else:
        df['is_invalid'] = 0

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
with engine.connect() as conn:
    code_df = pd.read_sql(sql, con=conn)
code_list = code_df.values.tolist()
STOCK_CODES = [x[0] for x in code_list]   # 例如 ['600000', '000001', ...]

STOCK_COLUMNS = ['code', 'name', 'zf_30', 'momentum', 'volume_change_rate', 'amount_now',
                   'zf_30_rank','momentum_rank','amount_rank','total_score_rank',
                   'zf_30_pct_rank', 'momentum_pct_rank', 'amount_pct_rank', 'volume_change_pct_rank',
                   'total_score','change_pct','change_pct_zq', 'rq', 'time', 'window_count']

# ========== 行业排行计算：模块级常量和缓存 ==========

# 行业排行结果列
INDUSTRY_RESULT_COLUMNS = [
    'code', 'name', 'count', 'total', 'avg_change_pct', 'avg_price', 'price_quality',
    'industry_cumulative_main_net',
    'raw_ratio', 'smooth_ratio', 'confidence', 'final_score', 'rank', 'rq', 'time'
]

# 价格质量因子默认参数
DEFAULT_PRICE_HALF_LIFE = 15.0  # A股中位价附近
DEFAULT_PRICE_WEIGHT = 0.5      # 温和影响

# ===== 价格区间筛选开关 =====
# True = 启用（按板块过滤价格区间：主板3-100、创业板5-200、科创板10-500、转债110-250）
# False = 关闭（不过滤，所有价格都参与上攻计算）
ENABLE_PRICE_FILTER = False

_industry_mapping_cache = None
_industry_mapping_cache_time = 0
_CACHE_TTL = 300  # 5分钟缓存

# ========== 涨停判断：模块级缓存 ==========
_ever_zt_cache: Set[str] = set()
_ever_zt_cache_date: str = ""

# ========== 表结构检查缓存（避免每tick查MySQL元数据） ==========
_table_schema_checked: Set[str] = set()
_table_schema_no_body: Set[str] = set()

# ========== 大盘阶段计算内存缓存 ==========
from collections import deque
_phase_history_map: dict = {}  # {table_name: deque}，支持多表（股票/债券各自独立缓存）

# ========== 异动检测：增量涨停 ==========
_prev_tick_zt_codes: Set[str] = set()
_prev_tick_zt_date: str = ""

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


# ========== 【性能优化】Redis数据快速验证（跳过完整清洗） ==========
def _quick_validate_redis_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    对从Redis/MySQL加载的历史数据做最小验证。
    这些数据在保存时已经过normalize_stock_dataframe清洗，无需重复清洗。
    仅确保stock_code为6位字符串格式（反序列化可能丢失前导零）。
    """
    if df is None or df.empty:
        return pd.DataFrame()
    if 'stock_code' in df.columns:
        df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
    return df


# ========== 【超短优化】向量化主力行为分类 ==========
def classify_main_force_behavior_vectorized(df: pd.DataFrame, time_of_day: dt_time) -> tuple:
    """
    向量化主力行为分类（超短交易优化版）。
    
    核心原则：direction 跟随 price_change_pct 的真实方向，
    仅在高确定性场景（涨停/炸板/拉高出货/尾盘异动）覆盖方向。
    
    Args:
        df: 包含 price_position, price_change_pct, volume_ratio, is_zt 列
            可选 is_zt_prev 列（用于炸板检测）
        time_of_day: 当前时间
    
    Returns:
        (direction, confidence, behavior) 三个 numpy 数组
    """
    n = len(df)
    pp = df['price_position'].values
    pcp = df['price_change_pct'].values
    vr = df['volume_ratio'].values
    iz = (df['is_zt'].values == 1) if 'is_zt' in df.columns else np.zeros(n, bool)
    
    # ========== 第1步：direction 由 pcp 直接决定 ==========
    direction = np.where(pcp >= 0.3, 1.0,
                np.where(pcp <= -0.3, -1.0,
                0.0))
    
    # ========== 第2步：confidence 由量能比+价格变化幅度决定 ==========
    vol_factor = np.clip(vr / 5.0, 0.0, 1.0)
    pcp_factor = np.where(np.abs(pcp) >= 0.5, 1.0,
                 np.where(np.abs(pcp) >= 0.3, 0.6,
                 0.0))
    confidence = np.round(vol_factor * pcp_factor, 2)
    
    # ========== 第3步：behavior 标签（描述性，不影响方向） ==========
    behavior = np.full(n, '', dtype=object)
    behavior = np.where((pp <= 0.3) & (pcp >= 0.3) & (vr >= 2),  '低位放量上涨', behavior)
    behavior = np.where((pp <= 0.3) & (pcp <= -0.3) & (vr >= 2), '低位放量下跌', behavior)
    behavior = np.where((pp >= 0.7) & (pcp >= 0.3) & (vr >= 2),  '高位放量上涨', behavior)
    behavior = np.where((pp >= 0.7) & (pcp <= -0.5) & (vr >= 2), '高位放量下跌', behavior)
    
    # ========== 第4步：高确定性覆盖（影响 direction） ==========
    is_early = dt_time(9, 30) <= time_of_day <= dt_time(10, 0)
    is_late = dt_time(14, 30) <= time_of_day <= dt_time(15, 0)
    
    # 4a. 涨停封板 → 强制 +1
    m_zt = iz & (pcp >= 0)
    direction = np.where(m_zt, 1.0, direction)
    confidence = np.where(m_zt, 0.85, confidence)
    behavior = np.where(m_zt & np.full(n, is_early), '早盘涨停', behavior)
    behavior = np.where(m_zt & ~np.full(n, is_early), '涨停封板', behavior)
    
    # 4b. 炸板 → 强制 -1
    if 'is_zt_prev' in df.columns:
        iz_prev = df['is_zt_prev'].values == 1
        m_broke = iz_prev & (~iz)
        direction = np.where(m_broke, -1.0, direction)
        confidence = np.where(m_broke, 0.85, confidence)
        behavior = np.where(m_broke, '炸板出货', behavior)
    
    # 4c. 拉高出货（极高位+急涨+极端放量）→ 强制 -1
    m_dump = (pp >= 0.98) & (pcp >= 1.0) & (vr >= 5)
    direction = np.where(m_dump, -1.0, direction)
    confidence = np.where(m_dump, 0.85, confidence)
    behavior = np.where(m_dump, '拉高出货', behavior)
    
    # 4d.【超短安全】尾盘放量上涨 → 强制 -1（隔夜诱多风控）
    m_late_pump = np.full(n, is_late) & (pcp >= 0.3) & (vr >= 2)
    direction = np.where(m_late_pump, -1.0, direction)
    confidence = np.where(m_late_pump, 0.60, confidence)
    behavior = np.where(m_late_pump, '尾盘异动', behavior)
    
    return direction, confidence, behavior


def calculate_participation_ratio_vectorized(delta_amount: np.ndarray) -> np.ndarray:
    """
    向量化版本的 calculate_participation_ratio，替代逐行 .apply()。
    逻辑与标量版本完全一致：分4个梯度的线性插值。
    """
    pts = MAIN_FORCE_CONFIG['participation_thresholds']
    t1, r1 = pts['level1']['amount'], pts['level1']['ratio']
    t2, r2 = pts['level2']['amount'], pts['level2']['ratio']
    t3, r3 = pts['level3']['amount'], pts['level3']['ratio']
    t4, r4 = pts['level4']['amount'], pts['level4']['ratio']
    
    da = np.asarray(delta_amount, dtype=float)
    return np.clip(
        np.where(da >= t4, r4,
        np.where(da >= t3, r3 + (da - t3) / (t4 - t3) * (r4 - r3),
        np.where(da >= t2, r2 + (da - t2) / (t3 - t2) * (r3 - r2),
        np.where(da >= t1, r1 + (da - t1) / (t2 - t1) * (r2 - r1),
        0.0)))),
        0.0, 1.0
    )


# ========== 累计字段通用继承 ==========
# 所有需要跨tick继承的累计字段及其默认值
CUMULATIVE_FIELDS = {
    'cumulative_main_net': 0.0,
    'main_net_count': 0,
    'max_cumulative_main_net': 0.0,
}


def _carry_forward_cumulative_fields(df_now: pd.DataFrame,
                                     df_prev_main: pd.DataFrame) -> pd.DataFrame:
    """
    无条件从上一tick继承所有累计字段。
    
    核心原则：不管本tick是否检测到主力活动，累计值必须被带到当前tick。
    性能：单次merge完成所有字段继承（约2ms/5000行）。
    """
    if df_prev_main is None or df_prev_main.empty:
        return df_now

    # 收集可用的累计字段
    available = [f for f in CUMULATIVE_FIELDS if f in df_prev_main.columns]
    if not available:
        return df_now

    # 准备prev数据（一次性提取所有累计字段）
    prev_data = df_prev_main[['stock_code'] + available].copy()
    prev_data['stock_code'] = prev_data['stock_code'].astype(str).str.strip().str.zfill(6)
    for field in available:
        prev_data[field] = pd.to_numeric(prev_data[field], errors='coerce').fillna(
            CUMULATIVE_FIELDS[field]
        )

    # 单次merge继承所有字段
    df_now['stock_code'] = df_now['stock_code'].astype(str).str.strip().str.zfill(6)
    df_now = df_now.merge(prev_data, on='stock_code', how='left', suffixes=('', '_prev_carry'))

    # 用继承值覆盖初始0值
    for field in available:
        carry_col = f'{field}_prev_carry'
        if carry_col in df_now.columns:
            default = CUMULATIVE_FIELDS[field]
            df_now[field] = df_now[carry_col].fillna(default)
            if isinstance(default, int):
                df_now[field] = df_now[field].astype(int)
            df_now.drop(columns=[carry_col], inplace=True)

    return df_now


def _recover_cumulative_from_mysql(df_now: pd.DataFrame, table_name: str,
                                   current_time: str) -> None:
    """
    【修复】程序重启后Redis无数据时，从MySQL恢复累计值。
    使用MAX聚合确保恢复的是全天最大值，而非最新时间点的值。
    直接修改df_now的累计字段（原地操作）。
    """
    try:
        stock_codes = df_now['stock_code'].tolist()
        if not stock_codes:
            return
        
        codes_str = ','.join([f"'{c}'" for c in stock_codes])
        
        # 【修复】使用MAX聚合，确保恢复的是全天最大值而非最新值
        query = f"""
            SELECT 
                stock_code,
                MAX(cumulative_main_net) as cumulative_main_net,
                MAX(max_cumulative_main_net) as max_cumulative_main_net,
                MAX(main_net_count) as main_net_count
            FROM {table_name}
            WHERE stock_code IN ({codes_str}) AND time < '{current_time}'
            GROUP BY stock_code
        """
        
        prev_data = pd.read_sql(query, con=engine)
        if prev_data.empty:
            logger.warning(f"MySQL恢复: 未找到 time < '{current_time}' 的历史数据")
            return
        
        prev_data['stock_code'] = prev_data['stock_code'].astype(str).str.strip().str.zfill(6)
        df_now['stock_code'] = df_now['stock_code'].astype(str).str.strip().str.zfill(6)
        
        recovered_count = 0
        for field, default in CUMULATIVE_FIELDS.items():
            if field in prev_data.columns:
                mapping = prev_data.set_index('stock_code')[field].to_dict()
                df_now[field] = df_now['stock_code'].map(mapping).fillna(default)
                recovered_count += (df_now[field] != default).sum()
        
        logger.info(f"从MySQL恢复累计值成功: {len(prev_data)}只股票, 非零值{recovered_count}个")
    except Exception as e:
        logger.warning(f"从MySQL恢复累计值失败: {e}")


def _save_cumulative_to_redis_hash(df_now: pd.DataFrame, sssj_table: str) -> None:
    """
    将当前累计值写入 Redis hash，供重启后快速恢复。
    key: {sssj_table}:cumulative
    field: stock_code
    value: "cumulative_main_net,max_cumulative_main_net,main_net_count"
    """
    try:
        client = redis_util._get_redis_client()
        hash_key = f"{sssj_table}:cumulative"
        
        # 只写入有非零累计值的股票（减少数据量）
        mask = (df_now['cumulative_main_net'] != 0) | (df_now['max_cumulative_main_net'] != 0) | (df_now['main_net_count'] != 0)
        df_write = df_now[mask]
        
        if df_write.empty:
            return
        
        mapping = {}
        for _, row in df_write.iterrows():
            code = str(row['stock_code']).strip().zfill(6)
            cum = float(row.get('cumulative_main_net', 0))
            max_cum = float(row.get('max_cumulative_main_net', 0))
            count = int(row.get('main_net_count', 0))
            mapping[code] = f"{cum},{max_cum},{count}"
        
        if mapping:
            client.hset(hash_key, mapping=mapping)
            client.expire(hash_key, 86400)  # 24h兜底过期
    except Exception as e:
        logger.warning(f"写入Redis累计值hash失败（非关键）: {e}")


def _recover_cumulative_from_redis_hash(df_now: pd.DataFrame, sssj_table: str) -> bool:
    """
    从 Redis hash 恢复累计值（应用重启时使用）。
    
    Returns:
        True=恢复成功, False=无数据或失败
    """
    try:
        client = redis_util._get_redis_client()
        hash_key = f"{sssj_table}:cumulative"
        
        raw_data = client.hgetall(hash_key)
        if not raw_data:
            return False
        
        # 解析 hash 数据
        cum_map = {}
        max_cum_map = {}
        count_map = {}
        for code_bytes, val_bytes in raw_data.items():
            code = code_bytes.decode() if isinstance(code_bytes, bytes) else code_bytes
            val = val_bytes.decode() if isinstance(val_bytes, bytes) else val_bytes
            parts = val.split(',')
            if len(parts) == 3:
                cum_map[code] = float(parts[0])
                max_cum_map[code] = float(parts[1])
                count_map[code] = int(float(parts[2]))
        
        if not cum_map:
            return False
        
        # 映射到 df_now
        df_now['stock_code'] = df_now['stock_code'].astype(str).str.strip().str.zfill(6)
        df_now['cumulative_main_net'] = df_now['stock_code'].map(cum_map).fillna(0.0)
        df_now['max_cumulative_main_net'] = df_now['stock_code'].map(max_cum_map).fillna(0.0)
        df_now['main_net_count'] = df_now['stock_code'].map(count_map).fillna(0).astype(int)
        
        recovered = (df_now['cumulative_main_net'] != 0).sum()
        logger.info(f"从Redis hash恢复累计值: {len(cum_map)}只股票在hash中, {recovered}只匹配成功")
        return recovered > 0
    except Exception as e:
        logger.warning(f"从Redis hash恢复累计值失败: {e}")
        return False


def calculate_main_force_and_cumulative(df_now: pd.DataFrame,
                                     df_prev_main: pd.DataFrame,
                                     day_stats: dict,
                                     time_of_day: dt_time) -> pd.DataFrame:
    """
    计算主力净额和累计主力净额（一体化）
    
    【修复】累计值继承与主力检测解耦：
    - 第0步：无条件继承上一tick的所有累计值
    - 第1步：计算本tick的主力净额增量
    - 第2步：在继承值基础上叠加增量
    
    Args:
        df_now: 当前时刻数据
        df_prev_main: 上一个有数据的时间点数据（时间戳查询获得）
        day_stats: 当日统计数据
        time_of_day: 当前时间
    
    Returns:
        DataFrame with main_net_amount, main_behavior, main_confidence, cumulative_main_net
    """
    # 初始化增量字段
    df_now['main_net_amount'] = 0.0
    df_now['main_behavior'] = '无主力'
    df_now['main_confidence'] = 0.0
    # 初始化累计字段（马上被继承覆盖）
    for field, default in CUMULATIVE_FIELDS.items():
        df_now[field] = default

    # ========== 第0步：无条件继承累计值 ==========
    df_now = _carry_forward_cumulative_fields(df_now, df_prev_main)

    if df_prev_main is None or df_prev_main.empty:
        return df_now  # 累计已继承（首tick为0，正确）

    try:
        # 【性能优化】df_prev_main的累计字段可能来自MySQL(Decimal类型)，需转换
        # 但price/volume/amount/change_pct已在上游清洗，无需重复转换
        if 'cumulative_main_net' in df_prev_main.columns:
            df_prev_main['cumulative_main_net'] = pd.to_numeric(
                df_prev_main['cumulative_main_net'], errors='coerce').fillna(0)
        if 'main_net_amount' in df_prev_main.columns:
            df_prev_main['main_net_amount'] = pd.to_numeric(
                df_prev_main['main_net_amount'], errors='coerce').fillna(0)

        # ========== 第1步：计算主力净额增量 ==========
        # 【超短优化】增加 is_zt 用于炸板检测
        prev_cols = ['stock_code', 'volume', 'amount', 'change_pct']
        if 'is_zt' in df_prev_main.columns:
            prev_cols.append('is_zt')
        
        merged = pd.merge(
            df_now[['stock_code', 'short_name', 'price', 'volume', 'amount', 'change_pct', 'is_zt']],
            df_prev_main[prev_cols],
            on='stock_code',
            suffixes=('_now', '_prev'),
            how='inner'
        )

        if merged.empty:
            return df_now  # ✅ 累计已继承，增量为0，安全返回

        # 【超短优化】重命名 is_zt 列：is_zt_now(当前), is_zt_prev(上一tick)
        if 'is_zt_now' in merged.columns:
            merged.rename(columns={'is_zt_now': 'is_zt'}, inplace=True)
        if 'is_zt_prev' not in merged.columns and 'is_zt' in df_prev_main.columns:
            # merge后没有is_zt_prev，说明df_prev_main没有is_zt列
            pass

        # 计算变化量
        merged['delta_amount'] = merged['amount_now'] - merged['amount_prev']
        merged['delta_volume'] = merged['volume_now'] - merged['volume_prev']
        merged['price_change_pct'] = merged['change_pct_now'] - merged['change_pct_prev']

        # 门槛过滤
        mask = (merged['delta_amount'] >= MAIN_FORCE_CONFIG['min_amount']) & \
               (merged['delta_volume'] >= MAIN_FORCE_CONFIG['min_volume'])
        valid_data = merged[mask].copy()

        if valid_data.empty:
            return df_now  # ✅ 累计已继承，增量为0，安全返回

        # 计算价格位置
        day_high = day_stats.get('day_high', valid_data['price'].max())
        day_low = day_stats.get('day_low', valid_data['price'].min())
        price_range = day_high - day_low if day_high > day_low else 1.0
        valid_data['price_position'] = ((valid_data['price'] - day_low) / price_range).clip(0, 1)

        # 计算量能比
        avg_volume = valid_data['delta_volume'].median() if len(valid_data) > 0 else 20000
        valid_data['volume_ratio'] = valid_data['delta_volume'] / avg_volume if avg_volume > 0 else 1.0

        # 【性能优化】向量化主力行为分类（替代逐行apply）
        direction, confidence, behavior = classify_main_force_behavior_vectorized(
            valid_data, time_of_day
        )
        valid_data['main_behavior'] = behavior
        valid_data['direction'] = direction
        valid_data['confidence'] = confidence

        # 【性能优化】向量化参与系数（替代逐行apply）
        valid_data['participation'] = calculate_participation_ratio_vectorized(
            valid_data['delta_amount'].values
        )
        valid_data['main_net_amount'] = (
            valid_data['delta_amount'] *
            valid_data['participation'] *
            valid_data['direction'] *
            valid_data['confidence']
        ).round(2)

        # 合并增量结果到df_now
        cols_to_drop = ['main_net_amount', 'main_behavior', 'main_confidence']
        for col in cols_to_drop:
            if col in df_now.columns:
                df_now = df_now.drop(columns=[col])

        result_cols = ['stock_code', 'main_net_amount', 'main_behavior', 'confidence']
        df_now = df_now.merge(valid_data[result_cols], on='stock_code', how='left')
        df_now['main_net_amount'] = df_now['main_net_amount'].fillna(0)
        df_now['main_behavior'] = df_now['main_behavior'].fillna('无主力')
        df_now['main_confidence'] = df_now['confidence'].fillna(0)
        df_now = df_now.drop(columns=['confidence'], errors='ignore')

        # ========== 第2步：在继承值基础上叠加增量 ==========
        df_now['cumulative_main_net'] = df_now['cumulative_main_net'] + df_now['main_net_amount']

        # 更新净额次数
        has_main_net = (df_now['main_net_amount'].abs() > 1e-6).astype(int)
        df_now['main_net_count'] = df_now['main_net_count'] + has_main_net

        # 更新峰值
        df_now['max_cumulative_main_net'] = df_now[
            ['max_cumulative_main_net', 'cumulative_main_net']
        ].max(axis=1)

        # 日志
        non_zero_main = (df_now['main_net_amount'].abs() > 1e-6).sum()
        non_zero_cum = (df_now['cumulative_main_net'] != 0).sum()
        non_zero_count = (df_now['main_net_count'] > 0).sum()
        logger.info(f"主力净额计算完成: main={non_zero_main}, cum={non_zero_cum}, count={non_zero_count}")

    except Exception as e:
        logger.error(f"计算主力净额失败: {e}")
        # ✅ 异常时累计值已经在第0步继承，不会丢失

    return df_now


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


# ========== 异动检测函数 ==========

def _anomaly_insert_async(trading_date, code, stock_name, time_full,
                           price, change_pct, consecutive,
                           related_industries, related_concepts, pre_messages, watchlist_info):
    """异步写入异动记录到MySQL（提交到线程池，不阻塞主循环）"""
    def _do_insert():
        try:
            from sqlalchemy import text as sa_text
            insert_sql = sa_text(
                "INSERT INTO stock_anomaly "
                "(trading_date, stock_code, stock_name, anomaly_type, anomaly_time, "
                "price, change_pct, continuous_zt, ai_status, "
                "related_industries, related_concepts, pre_forecast_messages, forecast_match) "
                "VALUES (:td, :sc, :sn, :at, :atime, :p, :cp, :cz, :st, :ri, :rc, :pm, :fm)"
            )
            params = {
                'td': trading_date, 'sc': code, 'sn': stock_name,
                'at': 'zt_hit', 'atime': time_full,
                'p': price, 'cp': change_pct, 'cz': consecutive, 'st': 'pending',
                'ri': json.dumps(related_industries, ensure_ascii=False) if related_industries else None,
                'rc': json.dumps(related_concepts, ensure_ascii=False) if related_concepts else None,
                'pm': pre_messages, 'fm': 'pending'
            }
            with engine.connect() as conn:
                conn.execute(insert_sql, params)
                conn.commit()
            logger.info(f"[异动] 首次涨停: {code} {stock_name} {time_full} "
                       f"涨幅{change_pct:.2f}% {'(watchlist命中)' if watchlist_info else '(突发)'}")
        except Exception as e:
            logger.warning(f"[异动] 写入失败 {code}: {e}")

    _fetch_executor.submit(_do_insert)
def _detect_anomaly_zt(zt_codes: Set[str], df_now: pd.DataFrame, date_str: str, time_full: str):
    """检测增量涨停并写入异动表（仅首次，Redis去重）
    
    Args:
        zt_codes: 当前tick所有涨停股票代码集合
        df_now: 当前tick的DataFrame
        date_str: 日期字符串（如 '20260622'）
        time_full: 完整时间字符串（如 '09:35:12'）
    """
    global _prev_tick_zt_codes, _prev_tick_zt_date

    # 日期变化时重置
    if date_str != _prev_tick_zt_date:
        _prev_tick_zt_codes = set()
        _prev_tick_zt_date = date_str

    # 增量涨停 = 当前涨停 - 上一tick涨停
    new_zt_codes = zt_codes - _prev_tick_zt_codes
    _prev_tick_zt_codes = zt_codes.copy()

    if not new_zt_codes:
        return

    # 格式化日期用于数据库
    trading_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    redis_key = f"anomaly:{trading_date}"

    try:
        redis_client = redis_util._get_redis_client()
    except Exception:
        return  # Redis不可用时静默跳过

    for code in new_zt_codes:
        # Redis 原子去重
        member = f"{code}:zt_hit"
        if redis_client.sadd(redis_key, member) != 1:
            continue  # 已记录过（如回封），跳过

        # 获取该股票的数据
        row = df_now[df_now['stock_code'] == code]
        if row.empty:
            continue
        r = row.iloc[0]

        stock_name = r.get('short_name', '')
        price = float(r.get('price', 0))
        change_pct = float(r.get('change_pct', 0))
        consecutive = int(r.get('consecutive_attacks', 0))

        # 查 watchlist 获取盘前预判消息
        watchlist_info = None
        try:
            wl_raw = redis_client.hget(f"anomaly:watchlist:{trading_date}", code)
            if wl_raw:
                watchlist_info = json.loads(wl_raw)
        except Exception:
            pass

        # 获取行业/概念
        related_industries = None
        related_concepts = None
        try:
            cache_raw = redis_client.hget("stock_industry_mapping", code)
            if cache_raw:
                cache_data = json.loads(cache_raw)
                related_industries = cache_data.get('industries')
                related_concepts = cache_data.get('concepts')
        except Exception:
            pass

        # 异步写入 MySQL 异动表（避免阻塞主循环）
        pre_messages = json.dumps(watchlist_info.get('messages'), ensure_ascii=False) if watchlist_info else None
        _anomaly_insert_async(
            trading_date, code, stock_name, time_full,
            price, change_pct, consecutive,
            related_industries, related_concepts, pre_messages, watchlist_info
        )

    # 设置Redis过期
    try:
        redis_client.expire(redis_key, 86400)
    except Exception:
        pass


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

    # 【性能优化】只复制merge需要的列，减少~80%复制量
    # 【修复】统一处理 stock_code/bond_code -> code，确保code列始终存在
    _cols_now = ['price', 'volume', 'amount', 'change_pct']
    if 'name' in df_now.columns:
        _cols_now.append('name')
    elif 'short_name' in df_now.columns:
        _cols_now.append('short_name')
    if 'main_net_amount' in df_now.columns:
        _cols_now.append('main_net_amount')
    # 必须保留原始代码列用于创建code
    if 'stock_code' in df_now.columns:
        _cols_now.append('stock_code')
    elif 'bond_code' in df_now.columns:
        _cols_now.append('bond_code')
    elif 'code' in df_now.columns:
        _cols_now.append('code')
    _cols_now = [c for c in _cols_now if c in df_now.columns]
    df_now = df_now[_cols_now].copy()
    
    _cols_prev = ['price', 'volume', 'amount', 'change_pct']
    if 'stock_code' in df_prev.columns:
        _cols_prev.append('stock_code')
    elif 'bond_code' in df_prev.columns:
        _cols_prev.append('bond_code')
    elif 'code' in df_prev.columns:
        _cols_prev.append('code')
    _cols_prev = [c for c in _cols_prev if c in df_prev.columns]
    df_prev = df_prev[_cols_prev].copy()

    # 【关键修复】在dropna之前创建统一的code列，确保始终存在
    if 'stock_code' in df_now.columns:
        df_now['code'] = df_now['stock_code'].astype(str)
    elif 'bond_code' in df_now.columns:
        df_now['code'] = df_now['bond_code'].astype(str)
    elif 'code' in df_now.columns:
        df_now['code'] = df_now['code'].astype(str)
    else:
        df_now['code'] = df_now.index.astype(str)
    
    if 'stock_code' in df_prev.columns:
        df_prev['code'] = df_prev['stock_code'].astype(str)
    elif 'bond_code' in df_prev.columns:
        df_prev['code'] = df_prev['bond_code'].astype(str)
    elif 'code' in df_prev.columns:
        df_prev['code'] = df_prev['code'].astype(str)
    else:
        df_prev['code'] = df_prev.index.astype(str)

    # 【P2-B】数据已在入口清洗，这里只做业务需要的dropna（code列已存在）
    df_now = df_now.dropna(subset=['price', 'volume', 'amount'])
    df_prev = df_prev.dropna(subset=['price', 'volume', 'amount'])

    # 删除原始代码列，只保留统一的code
    for col in ['stock_code', 'bond_code']:
        if col in df_now.columns:
            df_now = df_now.drop(columns=[col])
        if col in df_prev.columns:
            df_prev = df_prev.drop(columns=[col])

    # 统一 code 列类型为字符串（已在上面的映射中完成，这里确保）
    df_now['code'] = df_now['code'].astype(str)
    df_prev['code'] = df_prev['code'].astype(str)

    # 去重：数据源可能返回重复的代码记录，保留第一条
    df_now = df_now.drop_duplicates(subset=['code'], keep='first')
    df_prev = df_prev.drop_duplicates(subset=['code'], keep='first')

    # 合并两个时刻数据（内连接）
    merged = pd.merge(
        df_now[['code', 'name', 'price', 'volume', 'amount', 'change_pct']],
        df_prev[['code', 'price', 'volume', 'amount', 'change_pct']],
        on='code',
        suffixes=(f'_now', f'_prev'),
        how='inner',
        validate='1:1'  # 去重后代码唯一
    )
    if merged.empty:
        # 空数据返回空DataFrame（保持列结构）
        return pd.DataFrame(columns=STOCK_COLUMNS)

    # ---------- 【性能优化】动态价格区间（向量化替代Python循环） ----------
    if ENABLE_PRICE_FILTER:
        code_s = merged['code']
        is_main = code_s.str.match(r'^(600|601|603|605|000|001|002)')
        is_gem = code_s.str.startswith('300')
        is_star = code_s.str.startswith('688')
        is_bond = code_s.str.match(r'^(11|12)')
        
        merged['price_min'] = np.select([is_main, is_gem, is_star, is_bond], [3, 5, 10, 110], default=1)
        merged['price_max'] = np.select([is_main, is_gem, is_star, is_bond], [100, 200, 500, 250], default=1000)

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
    # 窗口涨幅（百分比）—— price_prev=0 替换为NaN，防止除以零
    safe_price_prev = merged['price_prev'].replace(0, float('nan'))
    merged['zf_30'] = ((merged['price_now'] - safe_price_prev) / safe_price_prev * 100).round(2)

    # 成交额变化率（带缩尾保护）—— amount_prev=0 替换为NaN
    amount_prev_abs = merged['amount_prev'].replace(0, float('nan')).abs()
    merged['amount_change_rate'] = ((merged['amount_now'] - merged['amount_prev']) / (amount_prev_abs + 1e-6)).round(2)
    # 成交量变化率 —— volume_prev=0 替换为NaN
    volume_prev_abs = merged['volume_prev'].replace(0, float('nan')).abs()
    merged['volume_change_rate'] = ((merged['volume_now'] - merged['volume_prev']) / (volume_prev_abs + 1e-6)).round(2)

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
            elif col in ('body_up', 'body_down', 'body_flat', 'is_body_up', 'is_body_down', 'is_body_flat'):
                # 【新增】实体红绿柱字段
                dtype_map[col] = sa_types.INT()
            elif col == 'body_up_down_ratio':
                # 【新增】红绿柱比
                dtype_map[col] = sa_types.DECIMAL(8, 2)
            elif col == 'open_price':
                # 【新增】开盘价
                dtype_map[col] = sa_types.DECIMAL(10, 2)
        
        # 使用 with engine.connect() 确保连接正确释放
        with engine.connect() as conn:
            df.to_sql(table_name, con=conn, if_exists='append', index=False,
                      method='multi', dtype=dtype_map)
            conn.commit()  # 显式提交事务
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
_mysql_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='mysql-store')
_redis_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='redis-store')
_dtype_cache = {}
_dtype_cache_lock = threading.Lock()


def _get_dtype_map(df: pd.DataFrame, table_name: str) -> dict:
    """
    获取DataFrame列到SQL类型的映射。
    【修复】禁用缓存，每次重新计算，确保新字段正确写入。
    
    Args:
        df: DataFrame
        table_name: 表名
    
    Returns:
        dict: 列名到SQLAlchemy类型的映射
    """
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
        elif col == 'main_net_count':
            dtype_map[col] = sa_types.INT()
        elif col == 'max_cumulative_main_net':
            dtype_map[col] = sa_types.FLOAT()
        elif col in ('body_up', 'body_down', 'body_flat', 'is_body_up', 'is_body_down', 'is_body_flat'):
            # 【新增】实体红绿柱字段
            dtype_map[col] = sa_types.INT()
        elif col == 'body_up_down_ratio':
            # 【新增】红绿柱比
            dtype_map[col] = sa_types.DECIMAL(8, 2)
        elif col == 'open_price':
            # 【新增】开盘价
            dtype_map[col] = sa_types.DECIMAL(10, 2)
    
    return dtype_map


def _ensure_mysql_columns(conn, table_name: str, df: pd.DataFrame, dtype_map: dict) -> None:
    """
    确保MySQL表包含DataFrame中的所有列，缺失的列自动添加。
    
    Args:
        conn: 数据库连接
        table_name: 表名
        df: DataFrame
        dtype_map: 列类型映射
    """
    from sqlalchemy import text, inspect
    
    inspector = inspect(conn)
    if not inspector.has_table(table_name):
        return  # 表不存在，to_sql会自动创建
    
    # 获取现有列
    existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
    
    # 找出缺失的列
    missing_cols = set(df.columns) - existing_columns
    
    if missing_cols:
        for col in missing_cols:
            col_type = dtype_map.get(col, sa_types.FLOAT())
            # 将SQLAlchemy类型转换为MySQL类型字符串
            if isinstance(col_type, sa_types.VARCHAR):
                mysql_type = f"VARCHAR({col_type.length})"
            elif isinstance(col_type, sa_types.DECIMAL):
                mysql_type = f"DECIMAL({col_type.precision},{col_type.scale})"
            elif isinstance(col_type, sa_types.INT):
                mysql_type = "INT"
            elif isinstance(col_type, sa_types.SMALLINT):
                mysql_type = "SMALLINT"
            else:
                mysql_type = "FLOAT"
            
            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN `{col}` {mysql_type}"
            conn.execute(text(alter_sql))
            logger.info(f"[异步存储] 表{table_name}添加列: {col} ({mysql_type})")


def _write_mysql_async(df: pd.DataFrame, table_name: str, dtype_map: dict) -> None:
    """
    MySQL写入（在后台线程执行）。
    【修复】使用 engine.begin() 确保事务正确提交，避免长事务。
    【修复】添加死锁重试机制，遇到1213错误自动重试。
    【修复】自动添加缺失的列，避免表结构不一致导致写入失败。
    
    Args:
        df: 要写入的DataFrame（已深拷贝）
        table_name: MySQL表名
        dtype_map: 列类型映射
    """
    import time as _time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with engine.begin() as conn:
                # 【新增】确保所有列都存在
                _ensure_mysql_columns(conn, table_name, df, dtype_map)
                df.to_sql(table_name, con=conn, if_exists='append',
                          index=False, method='multi', dtype=dtype_map)
            logger.info(f"[异步存储] MySQL写入完成: {table_name}，{len(df)}条")
            return
        except Exception as e:
            err_str = str(e)
            # 死锁(1213)或锁等待超时(1205)自动重试
            if ('1213' in err_str or '1205' in err_str) and attempt < max_retries - 1:
                _time.sleep(0.5 * (attempt + 1))
                logger.warning(f"[异步存储] MySQL死锁/超时，重试{attempt+2}/{max_retries}: {table_name}")
                continue
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
    _mysql_executor.submit(_write_mysql_async, df_copy, table_name, dtype_map)
    _redis_executor.submit(_write_redis_async, df_copy, table_name, time_full,
                             expire_seconds, use_compression)
    
    logger.info(f"[异步存储] 已提交: {table_name}:{time_full}，{len(df)}条")


def shutdown_storage() -> None:
    """
    程序退出前等待后台存储完成。
    
    确保所有提交的异步写入任务都执行完毕，避免数据丢失。
    """
    logger.info("等待后台存储任务完成...")
    _mysql_executor.shutdown(wait=True)
    _redis_executor.shutdown(wait=True)
    _storage_executor.shutdown(wait=True)  # 兼容旧引用
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
    (dt_time(9, 25,30), dt_time(9, 30)),   # 早盘集合竞价
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
    morning_start = dt_time(9, 25,30)
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
    # 【修改】使用精确的实体红绿柱统计（如果已计算）
    if 'is_body_up' in df_now.columns:
        body_up = int(df_now['is_body_up'].sum())
        body_down = int(df_now['is_body_down'].sum())
        body_flat = int(df_now['is_body_flat'].sum())
        body_up_down_ratio = round(body_up / body_down * 100, 2) if body_down > 0 else np.nan
    else:
        # 降级：用涨跌统计近似
        body_up = cur_up
        body_down = cur_down
        body_flat = cur_flat
        body_up_down_ratio = cur_up_down_ratio
    
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
        'min_up_down_ratio': min_up_down_ratio,
        # 【修改】使用精确的实体红绿柱统计
        'body_up': body_up,
        'body_down': body_down,
        'body_flat': body_flat,
        'body_up_down_ratio': body_up_down_ratio
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
        
        # 【修复】去重：数据源可能返回重复代码记录
        df_prev = df_prev.drop_duplicates(subset=['code'], keep='first')
        
        # 【优化】set_index + reindex替代merge
        prev_indexed = df_prev.set_index('code')['change_pct']
        now_codes = df_now['code'].unique()
        prev_matched = prev_indexed.reindex(now_codes)
        
        # 计算变化
        now_dedup = df_now.drop_duplicates(subset=['code'], keep='first')
        now_indexed = now_dedup.set_index('code')['change_pct']
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
    # 【修改】使用精确的实体红绿柱统计（如果已计算）
    if 'is_body_up' in df_now.columns:
        body_up = int(df_now['is_body_up'].sum())
        body_down = int(df_now['is_body_down'].sum())
        body_flat = int(df_now['is_body_flat'].sum())
        body_up_down_ratio = round(body_up / body_down * 100, 2) if body_down > 0 else np.nan
    else:
        # 降级：用涨跌统计近似
        body_up = cur_stats['up']
        body_down = cur_stats['down']
        body_flat = cur_stats['flat']
        body_up_down_ratio = cur_ratios['up_down']
    
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
        'min_up_down_ratio': min_ratios['up_down'],
        # 【修改】使用精确的实体红绿柱统计
        'body_up': body_up,
        'body_down': body_down,
        'body_flat': body_flat,
        'body_up_down_ratio': body_up_down_ratio
    }])
    
    # 【方案A】保持与原方案一致：比率列转为float
    ratio_cols = [
        'cur_up_ratio', 'cur_down_ratio', 'cur_flat_ratio', 'cur_up_down_ratio',
        'min_up_ratio', 'min_down_ratio', 'min_flat_ratio', 'min_up_down_ratio'
    ]
    result[ratio_cols] = result[ratio_cols].astype(float)
    
    return result


def _compute_phase_for_tick(engine, table_name, current_body_up, current_body_down,
                            current_min_up, current_min_down):
    """
    为当前 tick 计算大盘阶段（上升/下降/反弹/回落/震荡）。
    【优化】使用内存滑动窗口，仅首次或跨日时从MySQL回填。
    支持多表独立缓存（股票/债券各自维护）。
    """
    global _phase_history_map
    from sqlalchemy import text as sa_text

    # 获取或创建该表的缓存
    if table_name not in _phase_history_map:
        _phase_history_map[table_name] = deque(maxlen=160)
        # 首次：从MySQL回填
        try:
            with engine.connect() as conn:
                exists = conn.execute(sa_text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() AND table_name=:t"
                ), {'t': table_name}).fetchone()
                if exists:
                    rows = conn.execute(sa_text(
                        f"SELECT body_up, body_down, min_up, min_down "
                        f"FROM `{table_name}` ORDER BY time DESC LIMIT 159"
                    )).fetchall()
                    for row in rows:
                        _phase_history_map[table_name].append((int(row[0]), int(row[1]), int(row[2]), int(row[3])))
                    logger.info(f"[大盘阶段] {table_name} 从MySQL回填 {len(rows)} 条历史数据")
        except Exception:
            pass

    history = _phase_history_map[table_name]

    # 追加当前tick到队列头部
    current_tick = (int(current_body_up), int(current_body_down),
                    int(current_min_up), int(current_min_down))
    history.appendleft(current_tick)

    all_ticks = list(history)

    if len(all_ticks) < 20:
        return 'neutral', 'weak', 0.0

    recent = all_ticks[:60]      # 近期窗口（最近3分钟 ≈ 60tick）
    ref = all_ticks[60:160]      # 参照窗口（前5分钟 ≈ 100tick）

    def safe_ratio(up, down):
        total = up + down
        return up / total if total > 0 else None

    def avg_ratio(data, i_up, i_down):
        vals = [safe_ratio(r[i_up], r[i_down]) for r in data]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else 0.5

    recent_body = avg_ratio(recent, 0, 1)
    ref_body = avg_ratio(ref, 0, 1) if ref else recent_body
    recent_tick = avg_ratio(recent, 2, 3)
    ref_tick = avg_ratio(ref, 2, 3) if ref else recent_tick
    current_body = safe_ratio(all_ticks[0][0], all_ticks[0][1]) or 0.5

    # 动量 = 红柱趋势×0.6 + tick趋势×0.4
    momentum = (recent_body - ref_body) * 0.6 + (recent_tick - ref_tick) * 0.4
    abs_m = abs(momentum)

    # 判定
    state = 'bull' if current_body > 0.5 else 'bear'
    trend = 'improving' if momentum > 0 else 'weakening'

    PHASES = {
        ('bull', 'improving'): 'rising',
        ('bull', 'weakening'): 'pullback',
        ('bear', 'improving'): 'rebound',
        ('bear', 'weakening'): 'falling',
    }
    phase = PHASES[(state, trend)]
    if abs_m < 0.005:
        phase = 'neutral'

    strength = 'strong' if abs_m > 0.05 else ('medium' if abs_m > 0.02 else 'weak')

    return phase, strength, round(momentum, 6)


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
    
    # 【新增】实体红绿柱指标
    body_up_down_ratio = float(stats_row.get('body_up_down_ratio', cur_up_down_ratio))
    body_up = float(stats_row.get('body_up', 0))
    body_down = float(stats_row.get('body_down', 0))

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

    # --- 3. 市场状态划分（增加实体红绿柱状态）---
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
    
    # 【新增】实体红绿柱状态标签
    body_state = ""
    if not pd.isna(body_up_down_ratio) and body_up_down_ratio is not None:
        if body_up_down_ratio > 200:
            body_state = "多头强势"
        elif body_up_down_ratio > 150:
            body_state = "多头占优"
        elif body_up_down_ratio >= 67:
            body_state = "均衡"
        elif body_up_down_ratio >= 50:
            body_state = "空头占优"
        else:
            body_state = "空头强势"
    
    if body_state:
        state = f"{state}|{body_state}"

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


def _recover_invalid_data_vectorized(df_now, df_prev, invalid_codes, time_full):
    """
    【优化】向量化恢复无效数据，O(n)复杂度，比循环快100-1000倍
    
    Args:
        df_now: 当前tick的DataFrame（会被修改）
        df_prev: 前一tick的DataFrame
        invalid_codes: 无效股票代码列表
        time_full: 当前时间字符串
    
    Returns:
        int: 成功恢复的股票数量
    """
    if df_prev is None or df_prev.empty or not invalid_codes:
        return 0
    
    fields_to_recover = ['price', 'change_pct', 'volume', 'amount', 'change']
    available_fields = [f for f in fields_to_recover 
                       if f in df_prev.columns and f in df_now.columns]
    
    if not available_fields:
        return 0
    
    try:
        # 【向量化】构建恢复数据（只包含无效股票）
        prev_recovery = (df_prev[df_prev['stock_code'].isin(invalid_codes)]
                        .set_index('stock_code')[available_fields])
        
        if prev_recovery.empty:
            return 0
        
        # 【向量化】批量更新
        df_now_indexed = df_now.set_index('stock_code')
        df_now_indexed.update(prev_recovery)
        
        # 【向量化】标记已恢复的股票
        recovered_codes = prev_recovery.index.intersection(
            set(df_now[df_now['stock_code'].isin(invalid_codes)]['stock_code'])
        )
        df_now_indexed.loc[list(recovered_codes), 'is_invalid'] = 2
        
        # 恢复索引
        df_now_indexed.reset_index(inplace=True)
        
        # 将结果写回df_now
        for col in df_now_indexed.columns:
            if col in df_now.columns:
                df_now[col] = df_now_indexed[col]
        
        recovered_count = len(recovered_codes)
        if recovered_count > 0:
            logger.info(f"[{time_full}] 成功恢复 {recovered_count}/{len(invalid_codes)} 只")
        
        return recovered_count
        
    except Exception as e:
        logger.error(f"[{time_full}] 向量化恢复异常: {e}")
        return 0


def deal_gp_works(loop_start):
    """
    单个轮询周期的主处理函数：获取股票数据、存储实时数据、计算前30秒指标及大盘强度。
    【优化】添加6阶段性能监控

    Args:
        loop_start (datetime): 当前轮询开始时间。
    """
    # 【性能监控】Tick周期开始
    tick_start = time.time()
    
    # 添加时间字段（HH:MM:SS）
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")

    try:
        # ========== 阶段1：数据采集 ==========
        t1 = time.time()
        df_now = fetch_all_concurrently(STOCK_CODES)
        t1_elapsed = (time.time() - t1) * 1000
        
        if df_now.empty:
            # 数据为空，创建占位空DataFrame（包含后续计算所需的全部列）
            df_now = pd.DataFrame(columns=SOURCE_STOCK_FULL_COLUMNS)
        else:
            # 【P2-B优化】统一数据清洗
            if USE_UNIFIED_CLEAN:
                # ========== 阶段2：数据清洗 ==========
                t2 = time.time()
                df_now = normalize_stock_dataframe(df_now, required_cols=['stock_code', 'price'])
                t2_elapsed = (time.time() - t2) * 1000
                
                # ========== 阶段3：恢复无效数据（向量化优化） ==========
                t3 = time.time()
                recovered_count = 0
                if 'is_invalid' in df_now.columns and df_now['is_invalid'].sum() > 0:
                    invalid_codes = df_now[df_now['is_invalid']==1]['stock_code'].tolist()
                    
                    try:
                        from gs2026.utils import redis_util
                        sssj_table = f"monitor_gp_sssj_{date_str}"
                        prev_time = redis_util.get_prev_timestamp_with_data(sssj_table, time_full)
                        
                        if prev_time:
                            df_prev = redis_util.load_dataframe_by_time(sssj_table, prev_time)
                            recovered_count = _recover_invalid_data_vectorized(
                                df_now, df_prev, invalid_codes, time_full
                            )
                    except Exception as e:
                        logger.error(f"[{time_full}] 恢复异常: {e}")
                
                t3_elapsed = (time.time() - t3) * 1000
                
                logger.info(f"[{time_full}] 阶段耗时: 采集{t1_elapsed:.1f}ms | "
                           f"清洗{t2_elapsed:.1f}ms | 恢复{t3_elapsed:.1f}ms({recovered_count}只)")
            else:
                # 兼容旧逻辑
                df_now['stock_code'] = df_now['stock_code'].astype(str).str.zfill(6)
    except Exception as e:
        logger.error(f"获取股票数据异常: {e}")
        df_now = pd.DataFrame(columns=SOURCE_STOCK_FULL_COLUMNS)

    df_now['time'] = time_full

    # ========== 阶段4：计算开盘价和实体红绿柱 ==========
    t4 = time.time()
    if not df_now.empty:
        from gs2026.monitor.open_price_manager import ensure_open_prices, is_frozen
        
        # 确保开盘价（采集/冻结模式自动处理）
        df_now = ensure_open_prices(df_now, time_full, date_str)
        
        # 计算实体红绿柱
        df_now['is_body_up'] = (df_now['price'] > df_now['open_price']).astype(int)
        df_now['is_body_down'] = (df_now['price'] < df_now['open_price']).astype(int)
        df_now['is_body_flat'] = (df_now['price'] == df_now['open_price']).astype(int)
        
        # 统计日志
        if is_frozen():
            logger.debug(f"[{time_full}] 实体红绿柱 红:{df_now['is_body_up'].sum()} "
                        f"绿:{df_now['is_body_down'].sum()} 平:{df_now['is_body_flat'].sum()}")
        else:
            logger.info(f"[{time_full}] 实体红绿柱(采集期) 红:{df_now['is_body_up'].sum()} "
                       f"绿:{df_now['is_body_down'].sum()} 平:{df_now['is_body_flat'].sum()}")
    
    t4_elapsed = (time.time() - t4) * 1000

    # ========== 阶段5：计算涨停和主力净额 ==========
    t5 = time.time()
    if not df_now.empty:
        # 转换 change_pct 为数值
        df_now['change_pct'] = pd.to_numeric(df_now['change_pct'], errors='coerce')
        
        # 计算是否涨停
        if USE_VECTORIZED:
            code_col = df_now['code'] if 'code' in df_now.columns else df_now['stock_code']
            name_col = df_now.get('name', df_now.get('short_name'))
            df_now['is_zt'] = calc_is_zt_vectorized(df_now['change_pct'], code_col, name_col)
        else:
            df_now['is_zt'] = df_now.apply(
                lambda row: int(is_zt(
                    row.get('change_pct'), 
                    row.get('stock_code', ''),
                    row.get('short_name', '')
                )), 
                axis=1
            )
        
        # 更新曾经涨停缓存
        zt_codes = set(df_now[df_now['is_zt'] == 1]['stock_code'].tolist())
        update_ever_zt_cache(date_str, zt_codes)
        
        # 【性能优化】向量化计算是否曾经涨停（用isin替代逐行apply）
        df_now['ever_zt'] = df_now['stock_code'].isin(_ever_zt_cache).astype(int)
        
        logger.info(f"涨停统计: 当前涨停 {df_now['is_zt'].sum()} 只, "
                   f"曾经涨停 {df_now['ever_zt'].sum()} 只")

        # ========== 异动检测：增量涨停写入异动表 ==========
        _detect_anomaly_zt(zt_codes, df_now, date_str, time_full)

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

    # 【性能优化】df_prev来自Redis（已清洗数据），只做快速验证
    if df_prev is not None and not df_prev.empty:
        df_prev = _quick_validate_redis_data(df_prev)

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
                
                # 【性能优化】df_prev_main来自Redis（已清洗数据），只做快速验证
                if df_prev_main is not None and not df_prev_main.empty:
                    df_prev_main = _quick_validate_redis_data(df_prev_main)
        except Exception as e:
            logger.warning(f"[{time_full}] 获取上一时间点失败: {e}")
    
    # ========== 【修复】计算主力净额和累计值 ==========
    if not is_auction and df_prev_main is not None and not df_prev_main.empty:
        try:
            df_now = calculate_main_force_and_cumulative(
                df_now, df_prev_main, day_stats, loop_start.time()
            )
            non_zero_main = (df_now['main_net_amount'] != 0).sum()
            non_zero_cum = (df_now['cumulative_main_net'] != 0).sum()
            logger.info(f"[{time_full}] 主力净额计算完成: main={non_zero_main}, cum={non_zero_cum}")
            
            # 【新增】写入 Redis hash，供重启后快速恢复
            _save_cumulative_to_redis_hash(df_now, sssj_table)
        except Exception as e:
            logger.error(f"[{time_full}] 主力净额计算失败: {e}")
            # ✅ 增量归零，但继承累计值
            df_now['main_net_amount'] = 0.0
            df_now['main_behavior'] = '无主力'
            df_now['main_confidence'] = 0.0
            df_now = _carry_forward_cumulative_fields(df_now, df_prev_main)

    elif not is_auction:
        # 无上一时刻数据（程序重启等）→ 三级恢复
        df_now['main_net_amount'] = 0.0
        df_now['main_behavior'] = '无主力'
        df_now['main_confidence'] = 0.0
        for field, default in CUMULATIVE_FIELDS.items():
            df_now[field] = default
        
        recovered = False
        
        # 第1级：从 Redis hash 恢复（最快，应用重启但Redis未重启时有效）
        try:
            recovered = _recover_cumulative_from_redis_hash(df_now, sssj_table)
            if recovered:
                logger.info(f"[{time_full}] 已从Redis hash恢复累计值")
        except Exception as e:
            logger.warning(f"[{time_full}] Redis hash恢复失败: {e}")
        
        # 第2级：Redis hash无数据，从MySQL恢复（兜底）
        if not recovered:
            try:
                _recover_cumulative_from_mysql(df_now, sssj_table, time_full)
                logger.info(f"[{time_full}] 已从MySQL恢复累计值")
            except Exception as e:
                logger.warning(f"[{time_full}] MySQL恢复也失败，累计值置0: {e}")

    else:
        # 集合竞价期间：增量归零，但需区分早盘/尾盘
        df_now['main_net_amount'] = 0.0
        df_now['main_behavior'] = '无主力'
        df_now['main_confidence'] = 0.0

        if auction_period == 'afternoon':
            # 【修复】尾盘集合竞价（14:57-15:00）：继承累计值，仅跳过增量计算
            try:
                prev_time = redis_util.get_prev_timestamp_with_data(sssj_table, time_full)
                if prev_time:
                    df_prev_carry = redis_util.load_dataframe_by_time(sssj_table, prev_time)
                    if df_prev_carry is not None and not df_prev_carry.empty:
                        df_now = _carry_forward_cumulative_fields(df_now, df_prev_carry)
                        logger.info(f"[{time_full}] 尾盘集合竞价，继承累计值（来自{prev_time}）")
                    else:
                        for field, default in CUMULATIVE_FIELDS.items():
                            df_now[field] = default
                        logger.info(f"[{time_full}] 尾盘集合竞价，无前一tick数据，累计值置0")
                else:
                    for field, default in CUMULATIVE_FIELDS.items():
                        df_now[field] = default
                    logger.info(f"[{time_full}] 尾盘集合竞价，无时间戳，累计值置0")
            except Exception as e:
                for field, default in CUMULATIVE_FIELDS.items():
                    df_now[field] = default
                logger.warning(f"[{time_full}] 尾盘集合竞价继承累计值失败: {e}")
        else:
            # 早盘集合竞价（9:25-9:30）：累计值正确为0（新一天开始）
            for field, default in CUMULATIVE_FIELDS.items():
                df_now[field] = default
            logger.info(f"[{time_full}] 早盘集合竞价，主力净额置0")
    
    t5_elapsed = (time.time() - t5) * 1000

    # ========== 阶段6：保存数据和计算大盘强度 ==========
    t6 = time.time()
    
    # 计算并存储大盘强度，返回top30 code集合
    top30_codes = culculate_gp_apqd_top30(df_now, df_prev, date_str, time_full, loop_start, is_auction, is_early_morning)

    # 【新增】统一计算所有派生字段（连续上攻次数等）
    try:
        df_now = calculate_all_derived(df_now, df_prev_main, top30_codes)
    except Exception as e:
        logger.error(f"[{time_full}] 派生字段计算失败: {e}")

    # 【P1-B优化】异步保存包含主力净额、累计值和派生字段的数据
    # 【优化】检查表结构，缓存结果避免每tick查MySQL元数据
    if sssj_table not in _table_schema_checked:
        try:
            from sqlalchemy import inspect
            inspector = inspect(engine)
            if inspector.has_table(sssj_table):
                columns = [c['name'] for c in inspector.get_columns(sssj_table)]
                if 'is_body_up' not in columns:
                    _table_schema_no_body.add(sssj_table)
                    logger.info(f"[股票] 表{sssj_table}已存在且无is_body列，后续自动删除这些列")
            _table_schema_checked.add(sssj_table)
        except Exception as e:
            logger.warning(f"[股票] 检查表结构失败: {e}")
    
    if sssj_table in _table_schema_no_body:
        df_now = df_now.drop(columns=['is_body_up', 'is_body_down', 'is_body_flat', 'open_price'], errors='ignore')
    
    try:
        save_dataframe_async(df_now, sssj_table, time_full, EXPIRE_SECONDS)
        logger.info(f"[{time_full}] 已提交异步保存实时数据，共 {len(df_now)} 条")
    except Exception as e:
        logger.error(f"[{time_full}] 保存实时数据失败: {e}")
    
    t6_elapsed = (time.time() - t6) * 1000
    
    # ========== 【性能监控】Tick周期总计 ==========
    tick_total = (time.time() - tick_start) * 1000
    logger.info(f"[{time_full}] Tick总计: {tick_total:.1f}ms | "
                f"采集{t1_elapsed:.1f}ms | 清洗{t2_elapsed:.1f}ms | "
                f"恢复{t3_elapsed:.1f}ms | 开盘{t4_elapsed:.1f}ms | "
                f"主力{t5_elapsed:.1f}ms | 保存{t6_elapsed:.1f}ms")


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

    # 大盘平均涨幅
    judge30['avg_change_pct'] = round(df_now['change_pct'].mean(), 4)

    # ---------- 计算大盘阶段（上升/下降/反弹/回落/震荡） ----------
    try:
        phase, strength, momentum = _compute_phase_for_tick(
            engine, apqd_table,
            int(judge30['body_up'].iloc[0]), int(judge30['body_down'].iloc[0]),
            int(judge30['min_up'].iloc[0]), int(judge30['min_down'].iloc[0])
        )
        judge30['market_phase'] = phase
        judge30['phase_strength'] = strength
        judge30['phase_momentum'] = momentum
    except Exception as e:
        judge30['market_phase'] = 'neutral'
        judge30['phase_strength'] = 'weak'
        judge30['phase_momentum'] = 0.0
        logger.warning(f"[股票] 计算大盘阶段失败: {e}")

    save_dataframe_async(judge30, apqd_table, time_full, EXPIRE_SECONDS)

    # ---------- 计算前30榜单 ----------
    # 集合竞价期间不计算前30榜单（因为没有前30秒数据）
    top30_codes = set()
    if is_auction:
        logger.info(f"[集合竞价] {time_full} 跳过前30榜单计算")
    elif df_prev is not None and not df_prev.empty:
        top30_df = calculate_top30_v3(df_now, df_prev, loop_start)
        if not top30_df.empty:
            gp_top30_table = f"monitor_gp_top30_{date_str}"
            result_df = attack_conditions(top30_df, rank_name='stock', engine=engine, table_name=gp_top30_table)
            top30_codes = set(result_df['code'].astype(str).unique())
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
    
    return top30_codes

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
    hy_all_df = calculate_industry_topn(top30_df, df_now, date_str, time_full)
    if not hy_all_df.empty:
        hy_top30_table = f"monitor_hy_top30_{date_str}"
        # 保存全部行业数据到 MySQL/Redis
        save_dataframe_async(hy_all_df, hy_top30_table, time_full, EXPIRE_SECONDS)
        # 只取 TOP5 更新上攻排行计数
        hy_top5_df = hy_all_df.head(5)
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

        # mapped_count = (all_df['industry_code'] != '').sum()
        # logger.info(f"[{time_full}] 行业映射: {mapped_count}/{len(all_df)} 只股票")

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
        # 新增：累计主力净额sum聚合
        if 'cumulative_main_net' in valid_df.columns:
            agg_dict['cumulative_main_net'] = 'sum'

        industry_stats = valid_df.groupby(['industry_code', 'industry_name']).agg(agg_dict).reset_index()

        # 重命名列
        rename_map = {'change_pct': 'avg_change_pct', 'code': 'total'}
        if has_price:
            rename_map['price'] = 'avg_price'
        if 'cumulative_main_net' in industry_stats.columns:
            rename_map['cumulative_main_net'] = 'industry_cumulative_main_net'
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
        # 不再过滤 count > 0，保留所有行业（count=0的行业得分自然最低）

        # ========== 6. 保留全部行业（不再过滤表现差的行业） ==========
        good = industry_stats.copy()

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

        # ========== 8. 全部行业排序，向量化构建结果 ==========
        all_industries = good.sort_values('final_score', ascending=False).reset_index(drop=True)
        all_industries['rank'] = range(1, len(all_industries) + 1)
        all_industries['rq'] = date_str
        all_industries['time'] = time_full

        # 列重命名 + 选择
        result_df = all_industries.rename(columns={'industry_code': 'code', 'industry_name': 'name'})

        # 确保所有结果列存在
        for col in INDUSTRY_RESULT_COLUMNS:
            if col not in result_df.columns:
                result_df[col] = 0

        result_df = result_df[INDUSTRY_RESULT_COLUMNS]

        # 数值精度
        for col in ['avg_change_pct', 'avg_price', 'price_quality',
                     'raw_ratio', 'smooth_ratio', 'confidence', 'final_score',
                     'industry_cumulative_main_net']:
            if col in result_df.columns:
                result_df[col] = result_df[col].round(4)
        result_df['count'] = result_df['count'].astype(int)
        result_df['total'] = result_df['total'].astype(int)

        # 日志输出
        # logger.info(f"[{time_full}] 行业排行（共{len(result_df)}个行业）TOP5:")
        # for _, row in result_df.head(5).iterrows():
        #     logger.info(f"  第{row['rank']}名 {row['name']}: "
        #                f"上涨{row['count']}/{row['total']}, "
        #                f"均价{row['avg_price']:.1f}元, "
        #                f"涨幅{row['avg_change_pct']:.2f}%, "
        #                f"主力净额{row.get('industry_cumulative_main_net', 0):.0f}, "
        #                f"质量{row['price_quality']:.3f}, "
        #                f"得分{row['final_score']:.4f}")

        return result_df

    except Exception as e:
        logger.error(f"[{time_full}] 计算行业排行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return pd.DataFrame(columns=INDUSTRY_RESULT_COLUMNS)

def attack_conditions(top30_df: pd.DataFrame, rank_name: str = 'default',
                      engine=None, table_name: str = None):
    """
    上攻排行榜条件过滤
    :param top30_df: 输入DataFrame
    :param rank_name: 排行类型 (stock/bond)
    :param engine: 数据库引擎（用于宕机恢复）
    :param table_name: 表名（用于宕机恢复）
    :return: 过滤后的DataFrame
    """
    if top30_df.empty:
        return top30_df
    
    # 复制避免修改原数据
    result_df = top30_df.copy()
    
    if rank_name == 'stock':
        result_df = result_df[
            (result_df['amount_rank'] <= 500) &
            (result_df['zf_30'] >= 0.2) &
            (result_df['momentum'] >= 50) &
            (result_df['total_score_rank'] <= 60)
        ]
    elif rank_name == 'bond':
        result_df = result_df[
            (result_df['amount_rank'] <= 50) &
            (result_df['zf_30'] >= 0.2) &
            (result_df['momentum'] >= 50) &
            (result_df['total_score_rank'] <= 10)
        ]
    
    # 计算区间次数（新方案：内存缓存 + 数据库宕机恢复）
    if not result_df.empty:
        try:
            time_full = result_df['time'].iloc[0] if 'time' in result_df.columns else None
            date_str = result_df['rq'].iloc[0] if 'rq' in result_df.columns else None
            
            if time_full and date_str and engine:
                # 构建表名（如果未传入）
                if table_name is None:
                    prefix = 'monitor_gp_top30' if rank_name == 'stock' else 'monitor_zq_top30'
                    table_name = f"{prefix}_{date_str}"
                
                codes = result_df['code'].astype(str).tolist()
                
                # 批量恢复（宕机恢复用）
                _batch_recover_window_counts(codes, date_str, time_full, table_name, engine)
                
                # 内存递增并赋值
                window_start = _calculate_window_start(time_full)
                window_counts = []
                for _, row in result_df.iterrows():
                    code = str(row['code'])
                    key = (date_str, window_start, code)
                    _tick_window_cache[key] = _tick_window_cache.get(key, 0) + 1
                    window_counts.append(_tick_window_cache[key])
                
                result_df['window_count'] = window_counts
                
                # 【新增】写入 Redis hash，供实时查询使用
                try:
                    global _last_wc_window_start
                    redis_wc_key = f"{table_name}:wc"
                    client = redis_util._get_redis_client()
                    
                    # 跨区间检测：清空 hash 重新开始
                    if _last_wc_window_start and _last_wc_window_start != window_start:
                        client.delete(redis_wc_key)
                    _last_wc_window_start = window_start
                    
                    # 写入当前 tick 上攻品种的 window_count
                    wc_data = {str(c): str(w) for c, w in zip(codes, window_counts)}
                    if wc_data:
                        client.hset(redis_wc_key, mapping=wc_data)
                        client.expire(redis_wc_key, 86400)  # 24h兜底过期
                except Exception as e:
                    logger.warning(f"写入Redis window_count hash失败: {e}")
            else:
                result_df['window_count'] = 0
        except Exception as e:
            logger.warning(f"计算window_count失败: {e}")
            result_df['window_count'] = 0
    else:
        result_df['window_count'] = 0
    
    return result_df


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
        
        with engine.connect() as conn:
            # 检查表是否存在，不存在则创建
            check_sql = text(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = DATABASE() AND table_name = '{table_name}'
            """)
            result = conn.execute(check_sql)
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
                conn.execute(create_sql)
                conn.commit()
                logger.info(f"表 {table_name} 创建成功")
            
            # 先删除该日期的旧数据，避免重复
            delete_sql = text(f"DELETE FROM {table_name} WHERE date = '{date_str}'")
            conn.execute(delete_sql)
            conn.commit()
        
        # 插入新数据（使用 with engine.connect() 确保连接正确释放）
        with engine.connect() as conn:
            rank_df.to_sql(table_name, con=conn, if_exists='append', index=False)
            conn.commit()
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