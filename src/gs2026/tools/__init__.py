"""
工具模块

提供各种实用工具函数和常量。
"""

from gs2026.tools.filters import (
    DEEPSEEK_KEYWORDS,
    NEWS_FILTER_KEYWORDS,
    OFFICIAL_KEYWORDS,
    COUNTRY_KEYWORDS,
    RISK_KEYWORDS,
    contains_sensitive_word,
    filter_text,
    is_official_related,
    is_risk_related,
)
from gs2026.tools.validators import (
    is_valid_stock_code,
    is_main_board,
    is_gem,
    is_star,
    normalize_stock_code,
)

__all__ = [
    # 关键词
    "DEEPSEEK_KEYWORDS",
    "NEWS_FILTER_KEYWORDS",
    "OFFICIAL_KEYWORDS",
    "COUNTRY_KEYWORDS",
    "RISK_KEYWORDS",
    # 过滤函数
    "contains_sensitive_word",
    "filter_text",
    "is_official_related",
    "is_risk_related",
    # 验证函数
    "is_valid_stock_code",
    "is_main_board",
    "is_gem",
    "is_star",
    "normalize_stock_code",
]
