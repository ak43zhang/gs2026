"""
数据验证工具

提供股票代码验证和格式化功能。
"""

import re
from typing import Optional


def is_valid_stock_code(code: str) -> bool:
    """
    验证股票代码是否有效
    
    Args:
        code: 股票代码
        
    Returns:
        是否有效
        
    Example:
        >>> is_valid_stock_code("600001")
        True
        >>> is_valid_stock_code("300001")
        True
        >>> is_valid_stock_code("12345")
        False
    """
    if not code or not isinstance(code, str):
        return False
    
    # 6位数字
    if not re.match(r'^\d{6}$', code):
        return False
    
    # 检查前缀
    valid_prefixes = ('60', '00', '30', '68', '8', '4')
    return code.startswith(valid_prefixes)


def is_main_board(code: str) -> bool:
    """
    是否为主板股票
    
    Args:
        code: 股票代码
        
    Returns:
        是否主板
    """
    if not code:
        return False
    return code.startswith(('60', '00'))


def is_gem(code: str) -> bool:
    """
    是否为创业板股票
    
    Args:
        code: 股票代码
        
    Returns:
        是否创业板
    """
    if not code:
        return False
    return code.startswith('30')


def is_star(code: str) -> bool:
    """
    是否为科创板股票
    
    Args:
        code: 股票代码
        
    Returns:
        是否科创板
    """
    if not code:
        return False
    return code.startswith('68')


def is_bj(code: str) -> bool:
    """
    是否为北交所股票
    
    Args:
        code: 股票代码
        
    Returns:
        是否北交所
    """
    if not code:
        return False
    return code.startswith(('8', '4'))


def get_stock_type(code: str) -> str:
    """
    获取股票类型
    
    Args:
        code: 股票代码
        
    Returns:
        股票类型描述
    """
    if is_main_board(code):
        return "主板"
    elif is_gem(code):
        return "创业板"
    elif is_star(code):
        return "科创板"
    elif is_bj(code):
        return "北交所"
    else:
        return "未知"


def normalize_stock_code(code: str, include_market: bool = False) -> str:
    """
    规范化股票代码
    
    Args:
        code: 原始股票代码
        include_market: 是否包含市场前缀
        
    Returns:
        规范化后的代码
        
    Example:
        >>> normalize_stock_code("600001")
        '600001'
        >>> normalize_stock_code("600001", include_market=True)
        'SH.600001'
    """
    if not code:
        return ""
    
    # 移除空格和点号
    code = code.strip().replace(".", "")
    
    # 移除市场前缀
    if code.startswith(('SH.', 'SZ.', 'BJ.', 'sh.', 'sz.', 'bj.')):
        code = code[3:]
    if code.startswith(('SH', 'SZ', 'BJ', 'sh', 'sz', 'bj')):
        code = code[2:]
    
    if not include_market:
        return code
    
    # 添加市场前缀
    if code.startswith('6'):
        return f"SH.{code}"
    elif code.startswith(('0', '3')):
        return f"SZ.{code}"
    elif code.startswith(('8', '4')):
        return f"BJ.{code}"
    else:
        return code


def add_market_prefix(code: str) -> str:
    """
    为股票代码添加市场前缀
    
    Args:
        code: 股票代码
        
    Returns:
        带市场前缀的代码
        
    Example:
        >>> add_market_prefix("600001")
        'SH.600001'
        >>> add_market_prefix("300001")
        'SZ.300001'
    """
    return normalize_stock_code(code, include_market=True)


def remove_market_prefix(code: str) -> str:
    """
    移除股票代码的市场前缀
    
    Args:
        code: 股票代码
        
    Returns:
        纯数字代码
        
    Example:
        >>> remove_market_prefix("SH.600001")
        '600001'
    """
    return normalize_stock_code(code, include_market=False)
