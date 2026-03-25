"""
股债关联数据获取 - 基于债券时间戳的精确匹配

核心设计：
1. 只查询 Redis，精确匹配
2. 时间固定为 3 秒间隔（由 monitor_stock 存储）
3. 超过时间区间则跳过
4. 以债券为核心管理
5. 每 0.1s 轮询 Redis 直到找到或超时
"""

import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pandas as pd
from loguru import logger

from gs2026.utils import redis_util


def fetch_aligned_stock_by_bond(
    bond_code: str,
    stock_code: str,
    max_wait: float = 3.0,
    poll_interval: float = 0.1
) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
    """
    基于债券时间戳获取对齐的股票数据
    
    流程：
    1. 获取债券数据（快）
    2. 用债券时间戳轮询 Redis 查找股票数据
    3. 找到或超时返回
    
    Args:
        bond_code: 债券代码
        stock_code: 股票代码
        max_wait: 最大等待时间（秒）
        poll_interval: 轮询间隔（秒）
    
    Returns:
        (bond_df, stock_df) 或 None
    """
    date_str = datetime.now().strftime('%Y%m%d')
    bond_table = f"monitor_zq_sssj_{date_str}"
    stock_table = f"monitor_gp_sssj_{date_str}"
    
    # ========== 步骤1: 获取债券数据 ==========
    bond_df = _fetch_from_redis(bond_table, bond_code)
    if bond_df is None or bond_df.empty:
        return None
    
    bond_time = bond_df['time'].iloc[0]
    
    # ========== 步骤2: 轮询查找股票数据 ==========
    start_time = time.time()
    stock_df = None
    
    while (time.time() - start_time) < max_wait:
        stock_df = _fetch_from_redis(stock_table, stock_code, bond_time)
        
        if stock_df is not None and not stock_df.empty:
            # 找到数据，验证时间一致性
            stock_time = stock_df['time'].iloc[0]
            if stock_time == bond_time:
                logger.info(f"关联成功: 债券={bond_time}, 股票={stock_time}")
                return bond_df, stock_df
        
        # 未找到，等待后重试
        time.sleep(poll_interval)
    
    # 超时未找到
    elapsed = time.time() - start_time
    logger.warning(f"关联超时: 债券={bond_time}, 等待={elapsed:.2f}s, 未找到股票数据")
    return None


def _fetch_from_redis(
    table_name: str,
    code: str,
    time_str: Optional[str] = None
) -> Optional[pd.DataFrame]:
    """
    从 Redis 获取数据
    
    Args:
        table_name: 表名
        code: 代码
        time_str: 指定时间（为None则取最新）
    
    Returns:
        DataFrame 或 None
    """
    try:
        # 获取时间戳列表
        timestamps_key = f"{table_name}:timestamps"
        client = redis_util._get_redis_client()
        times = client.lrange(timestamps_key, 0, -1)
        
        if not times:
            return None
        
        # 确定查询时间
        if time_str:
            # 精确匹配指定时间
            target_time = time_str
        else:
            # 取最新时间
            target_time = times[0].decode() if isinstance(times[0], bytes) else times[0]
        
        # 查询 Redis
        redis_key = f"{table_name}:{target_time}"
        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
        
        if df is None or df.empty:
            return None
        
        # 过滤指定代码
        code_col = 'bond_code' if 'bond' in table_name else 'stock_code'
        df = df[df[code_col] == code]
        
        return df if not df.empty else None
        
    except Exception as e:
        logger.error(f"Redis 查询失败 {table_name}:{code}: {e}")
        return None
