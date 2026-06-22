"""
涨停规则管理模块

集中管理所有涨停/跌停幅度规则，支持：
- 沪深主板：10%
- 创业板(300/301)：20%
- 科创板(688)：20%
- 北交所(8/9/920开头)：30%
- ST/*ST：5%

用法：
    from gs2026.monitor.module.zt_limit import is_zt, get_zt_limit
    
    # 判断是否涨停
    if is_zt(change_pct=19.5, code='300001', name='特锐德'):
        print("涨停！")
    
    # 获取涨停幅度
    limit = get_zt_limit('688001')  # 返回 20.0
"""

from typing import Optional
import numpy as np
import pandas as pd


def get_zt_limit(code: str, name: Optional[str] = None) -> float:
    """
    获取股票涨停幅度限制
    
    Args:
        code: 股票代码 (如 '000001', '300001', '688001')
        name: 股票名称 (用于判断ST)
    
    Returns:
        涨停幅度百分比 (如 10.0, 20.0, 30.0, 5.0)
    """
    # 1. ST/*ST 股票判断（最优先）
    if name and ('ST' in name or '*ST' in name):
        return 5.0
    
    # 2. 根据代码前缀判断板块
    if code.startswith('688'):  # 科创板
        return 20.0
    elif code.startswith(('300', '301')):  # 创业板
        return 20.0
    elif code.startswith('920'):  # 北交所新代码段
        return 30.0
    elif code.startswith(('8', '9')):  # 北交所
        return 30.0
    else:  # 沪深主板 (60, 00, 000, 001, 002, 003等)
        return 10.0


def is_zt(change_pct: float, code: str, name: Optional[str] = None,
          threshold: float = 0.1) -> bool:
    """
    判断是否涨停
    
    Args:
        change_pct: 当前涨跌幅百分比
        code: 股票代码
        name: 股票名称
        threshold: 判断阈值（默认0.1，即差0.1%算涨停）
    
    Returns:
        True=涨停, False=未涨停
    """
    # 处理None/NaN
    if change_pct is None or pd.isna(change_pct):
        return False
    
    limit = get_zt_limit(code, name)
    return change_pct >= (limit - threshold)


def is_dt(change_pct: float, code: str, name: Optional[str] = None,
          threshold: float = 0.1) -> bool:
    """
    判断是否跌停
    
    Args: 同 is_zt
    
    Returns:
        True=跌停, False=未跌停
    """
    if change_pct is None or pd.isna(change_pct):
        return False
    
    limit = get_zt_limit(code, name)
    return change_pct <= (-limit + threshold)


# ========== 向量化版本（用于pandas DataFrame） ==========

def get_zt_limit_vectorized(codes: pd.Series, names: Optional[pd.Series] = None) -> pd.Series:
    """
    向量化获取涨停幅度
    
    Args:
        codes: 股票代码Series
        names: 股票名称Series（可选）
    
    Returns:
        涨停幅度Series
    """
    def _get_limit(code, name):
        if name and ('ST' in name or '*ST' in name):
            return 5.0
        if code.startswith('688'):
            return 20.0
        elif code.startswith(('300', '301')):
            return 20.0
        elif code.startswith('920'):
            return 30.0
        elif code.startswith(('8', '9')):
            return 30.0
        else:
            return 10.0
    
    if names is not None:
        return pd.Series([
            _get_limit(c, n) for c, n in zip(codes, names)
        ], index=codes.index)
    else:
        return codes.apply(lambda c: _get_limit(c, None))


def calc_is_zt_vectorized(change_pcts: pd.Series, codes: pd.Series,
                          names: Optional[pd.Series] = None,
                          threshold: float = 0.1) -> pd.Series:
    """
    向量化判断是否涨停
    
    Args:
        change_pcts: 涨跌幅Series
        codes: 股票代码Series
        names: 股票名称Series（可选）
        threshold: 判断阈值
    
    Returns:
        是否涨停Series (1=涨停, 0=未涨停)
    """
    limits = get_zt_limit_vectorized(codes, names)
    return ((change_pcts >= (limits - threshold)) & (limits > 0)).astype(int)
