# -*- coding: utf-8 -*-
"""
向量化优化函数 - 第一阶段实施
"""

import numpy as np
import pandas as pd
from datetime import time as dt_time


def calc_is_zt_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    向量化涨停判断
    
    Args:
        df: DataFrame包含 stock_code, change_pct, short_name
    
    Returns:
        Series of int (1=涨停, 0=未涨停)
    """
    # 提取代码前缀
    code_prefix = df['stock_code'].str[:3]
    
    # 判断是否ST
    is_st = df['short_name'].str.contains('ST', na=False)
    
    # 判断涨停幅度
    zt_limit = np.where(
        code_prefix.isin(['300', '301', '688']),  # 创业板/科创板
        20.0,
        np.where(is_st, 5.0, 10.0)  # ST股5%，其他10%
    )
    
    # 判断是否涨停（涨跌幅 >= 涨停幅度 - 0.1）
    is_zt = df['change_pct'] >= (zt_limit - 0.1)
    
    return is_zt.astype(int)


def calculate_participation_ratio_vectorized(delta_amount: pd.Series) -> pd.Series:
    """
    向量化计算主力参与系数
    
    Args:
        delta_amount: 成交额变化Series
    
    Returns:
        参与系数Series
    """
    participation = pd.Series(0.0, index=delta_amount.index)
    
    # level4: >=200万 -> 1.0
    mask4 = delta_amount >= 2000000
    participation[mask4] = 1.0
    
    # level3: 100-200万 -> 0.8-1.0
    mask3 = (delta_amount >= 1000000) & (delta_amount < 2000000) & ~mask4
    participation[mask3] = 0.8 + (delta_amount[mask3] - 1000000) / 1000000 * 0.2
    
    # level2: 50-100万 -> 0.5-0.8
    mask2 = (delta_amount >= 500000) & (delta_amount < 1000000) & ~mask4 & ~mask3
    participation[mask2] = 0.5 + (delta_amount[mask2] - 500000) / 500000 * 0.3
    
    # level1: 30-50万 -> 0.3-0.5
    mask1 = (delta_amount >= 300000) & (delta_amount < 500000) & ~mask4 & ~mask3 & ~mask2
    participation[mask1] = 0.3 + (delta_amount[mask1] - 300000) / 200000 * 0.2
    
    # <30万 -> 0.0 (默认)
    
    return participation
