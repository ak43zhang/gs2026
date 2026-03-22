"""
常量管理模块

项目常量集中管理，方便维护和扩展。
所有常量在此模块中定义，通过统一接口导出。

使用示例:
    >>> from gs2026.constants import MARKET_SH, CODE_PREFIX_GEM
    >>> from gs2026.constants import get_market_by_code, is_main_board
    >>> 
    >>> market = get_market_by_code("600001")  # 返回 "SH"
    >>> is_gem = is_gem("300001")  # 返回 True

常量分类:
    - 代码前缀: CODE_PREFIX_*
    - 市场类型: MARKET_*
    - 股票类型: STOCK_*
    - 数据来源: SOURCE_*
    - 数据频率: FREQ_*
    - 分析类型: ANALYSIS_*
    - 风险等级: RISK_*
    - 信号类型: SIGNAL_*
    - 格式常量: *_FMT, ENCODING_*
    - 数据库表: TABLE_*
    - 缓存时间: CACHE_*
    - 系统常量: DEFAULT_*
    - SQL查询: SQL_*
    - 浏览器路径: FIREFOX_*, CHROME_*
"""

# =============================================================================
# 股票代码前缀
# =============================================================================
# 用于识别股票所属市场和板块

CODE_PREFIX_SH: str = "60"      #: 上海主板代码前缀 (600xxx, 601xxx, 603xxx)
CODE_PREFIX_SZ: str = "00"      #: 深圳主板代码前缀 (000xxx, 001xxx, 002xxx)
CODE_PREFIX_GEM: str = "30"     #: 创业板代码前缀 (300xxx, 301xxx)
CODE_PREFIX_STAR: str = "68"    #: 科创板代码前缀 (688xxx, 689xxx)
CODE_PREFIX_BJ: str = "8"       #: 北交所代码前缀 (8xxxx, 4xxxx)


# =============================================================================
# 市场类型
# =============================================================================
# 中国A股市场分类

MARKET_SH: str = "SH"           #: 上海证券交易所
MARKET_SZ: str = "SZ"           #: 深圳证券交易所
MARKET_BJ: str = "BJ"           #: 北京证券交易所
MARKET_HK: str = "HK"           #: 香港交易所


# =============================================================================
# 股票类型
# =============================================================================
# 按板块分类的股票类型

STOCK_MAIN: str = "main"        #: 主板 (上海主板 + 深圳主板)
STOCK_GEM: str = "gem"          #: 创业板 (Growth Enterprise Market)
STOCK_STAR: str = "star"        #: 科创板 (STAR Market)
STOCK_BJ: str = "bj"            #: 北交所 (北京证券交易所)


# =============================================================================
# 数据来源
# =============================================================================
# 支持的数据采集源

SOURCE_AKSHARE: str = "akshare"     #: AKShare 开源财经数据接口库
SOURCE_BAOSTOCK: str = "baostock"   #: Baostock 免费证券数据
SOURCE_TUSHARE: str = "tushare"     #: Tushare 财经数据接口
SOURCE_EASTMONEY: str = "eastmoney" #: 东方财富数据


# =============================================================================
# 数据频率
# =============================================================================
# 时间序列数据的频率

FREQ_DAILY: str = "daily"       #: 日线数据
FREQ_WEEKLY: str = "weekly"     #: 周线数据
FREQ_MINUTE: str = "1min"       #: 分钟线数据


# =============================================================================
# 分析类型
# =============================================================================
# 数据分析方法分类

ANALYSIS_TECH: str = "technical"    #: 技术分析
ANALYSIS_FUND: str = "fundamental"  #: 基本面分析
ANALYSIS_AI: str = "ai"             #: AI智能分析


# =============================================================================
# 风险等级
# =============================================================================
# 投资风险评估等级 (1-5级)

RISK_LOW: int = 1           #: 低风险
RISK_MEDIUM: int = 3        #: 中等风险
RISK_HIGH: int = 5          #: 高风险


# =============================================================================
# 信号类型
# =============================================================================
# 交易信号

SIGNAL_BUY: str = "buy"     #: 买入信号
SIGNAL_SELL: str = "sell"   #: 卖出信号
SIGNAL_HOLD: str = "hold"   #: 持有信号


# =============================================================================
# 格式常量
# =============================================================================
# 日期时间格式字符串

TIME_FMT: str = "%Y-%m-%d %H:%M:%S"     #: 标准时间格式
DATE_FMT: str = "%Y-%m-%d"              #: 标准日期格式
ENCODING_UTF8: str = "utf-8"            #: UTF-8编码


# =============================================================================
# 数据库表名
# =============================================================================
# 数据库表名常量

TABLE_STOCK: str = "stocks"         #: 股票基础信息表
TABLE_PRICE: str = "stock_prices"   #: 股票价格数据表
TABLE_LIMIT_UP: str = "limit_up"    #: 涨停数据表


# =============================================================================
# 缓存TTL (秒)
# =============================================================================
# 缓存过期时间

CACHE_1MIN: int = 60        #: 1分钟缓存
CACHE_5MIN: int = 300       #: 5分钟缓存
CACHE_1HOUR: int = 3600     #: 1小时缓存
CACHE_1DAY: int = 86400     #: 1天缓存


# =============================================================================
# 系统常量
# =============================================================================
# 系统默认参数

DEFAULT_TIMEOUT: int = 30           #: 默认超时时间(秒)
DEFAULT_RETRY: int = 3              #: 默认重试次数
DEFAULT_BATCH_SIZE: int = 100       #: 默认批量大小


# =============================================================================
# SQL查询语句
# =============================================================================
# 预定义的SQL查询

SQL_STOCK_MAIN_GEM: str = """
SELECT stock_code, list_date 
FROM data_agdm 
WHERE (stock_code LIKE '00%' OR stock_code LIKE '60%' OR stock_code LIKE '30%') 
  AND short_name NOT LIKE '%ST%' 
  AND short_name NOT LIKE '%退%' 
  AND list_date IS NOT NULL
""".strip()
"""主板+创业板股票查询 (排除ST和退市股票)"""

SQL_STOCK_MAIN_ONLY: str = """
SELECT stock_code, list_date 
FROM data_agdm 
WHERE (stock_code LIKE '00%' OR stock_code LIKE '60%') 
  AND short_name NOT LIKE '%ST%' 
  AND short_name NOT LIKE '%退%' 
  AND list_date IS NOT NULL
""".strip()
"""仅主板股票查询 (排除ST和退市股票)"""

SQL_STOCK_ALL: str = """
SELECT stock_code, list_date 
FROM data_agdm 
WHERE list_date IS NOT NULL
""".strip()
"""所有有上市日期的股票查询"""

SQL_STOCK_EXCLUDE_LARGE: str = """
SELECT stock_code, list_date 
FROM data_agdm 
WHERE (stock_code LIKE '00%' OR stock_code LIKE '60%' OR stock_code LIKE '30%') 
  AND short_name NOT LIKE '%ST%' 
  AND short_name NOT LIKE '%退%' 
  AND list_date IS NOT NULL 
  AND stock_code NOT IN (SELECT `代码` FROM dashizhi_20250224)
""".strip()
"""排除大市值股票的查询"""


# =============================================================================
# 浏览器路径
# =============================================================================
# Playwright浏览器可执行文件路径

import getpass
import os

_USER: str = getpass.getuser()
_BASE_PATH: str = f"C:/Users/{_USER}/AppData/Local/ms-playwright"

# Firefox 版本路径
FIREFOX_1408: str = os.path.join(_BASE_PATH, "firefox-1408/firefox/firefox.exe")
FIREFOX_1466: str = os.path.join(_BASE_PATH, "firefox-1466/firefox/firefox.exe")
FIREFOX_1509: str = os.path.join(_BASE_PATH, "firefox-1509/firefox/firefox.exe")

# Chromium 版本路径
CHROME_1208: str = os.path.join(_BASE_PATH, "chromium-1208/chrome-win64/chrome.exe")

# 默认浏览器
DEFAULT_FIREFOX: str = FIREFOX_1466
DEFAULT_CHROME: str = CHROME_1208


# =============================================================================
# 辅助函数
# =============================================================================

def get_market_by_code(code: str) -> str:
    """
    根据股票代码获取市场类型
    
    Args:
        code: 股票代码 (如 "600001", "300001")
        
    Returns:
        市场类型 (MARKET_SH, MARKET_SZ, MARKET_BJ)
        
    Example:
        >>> get_market_by_code("600001")
        'SH'
        >>> get_market_by_code("300001")
        'SZ'
    """
    if not code:
        return MARKET_SH
    first = code[0]
    if first == "6":
        return MARKET_SH
    elif first in ("0", "3"):
        return MARKET_SZ
    elif first == "8":
        return MARKET_BJ
    return MARKET_SH


def get_stock_type_by_code(code: str) -> str:
    """
    根据股票代码获取股票类型
    
    Args:
        code: 股票代码 (如 "600001", "300001")
        
    Returns:
        股票类型 (STOCK_MAIN, STOCK_GEM, STOCK_STAR, STOCK_BJ)
        
    Example:
        >>> get_stock_type_by_code("600001")
        'main'
        >>> get_stock_type_by_code("300001")
        'gem'
    """
    if not code or len(code) < 3:
        return STOCK_MAIN
    prefix = code[:3]
    if prefix.startswith("30"):
        return STOCK_GEM
    elif prefix.startswith("68"):
        return STOCK_STAR
    elif prefix.startswith("8"):
        return STOCK_BJ
    return STOCK_MAIN


def is_main_board(code: str) -> bool:
    """
    判断是否为主板股票
    
    Args:
        code: 股票代码
        
    Returns:
        是否主板 (上海主板 60xxxx 或 深圳主板 00xxxx)
        
    Example:
        >>> is_main_board("600001")
        True
        >>> is_main_board("300001")
        False
    """
    return code.startswith(("60", "00"))


def is_gem(code: str) -> bool:
    """
    判断是否为创业板股票
    
    Args:
        code: 股票代码
        
    Returns:
        是否创业板 (30xxxx)
        
    Example:
        >>> is_gem("300001")
        True
    """
    return code.startswith("30")


def is_star(code: str) -> bool:
    """
    判断是否为科创板股票
    
    Args:
        code: 股票代码
        
    Returns:
        是否科创板 (68xxxx)
        
    Example:
        >>> is_star("688001")
        True
    """
    return code.startswith("68")


# =============================================================================
# 导出列表
# =============================================================================

__all__ = [
    # 代码前缀
    "CODE_PREFIX_SH", "CODE_PREFIX_SZ", "CODE_PREFIX_GEM",
    "CODE_PREFIX_STAR", "CODE_PREFIX_BJ",
    # 市场
    "MARKET_SH", "MARKET_SZ", "MARKET_BJ", "MARKET_HK",
    # 股票类型
    "STOCK_MAIN", "STOCK_GEM", "STOCK_STAR", "STOCK_BJ",
    # 数据来源
    "SOURCE_AKSHARE", "SOURCE_BAOSTOCK", "SOURCE_TUSHARE", "SOURCE_EASTMONEY",
    # 数据频率
    "FREQ_DAILY", "FREQ_WEEKLY", "FREQ_MINUTE",
    # 分析类型
    "ANALYSIS_TECH", "ANALYSIS_FUND", "ANALYSIS_AI",
    # 风险等级
    "RISK_LOW", "RISK_MEDIUM", "RISK_HIGH",
    # 信号
    "SIGNAL_BUY", "SIGNAL_SELL", "SIGNAL_HOLD",
    # 格式
    "TIME_FMT", "DATE_FMT", "ENCODING_UTF8",
    # 表名
    "TABLE_STOCK", "TABLE_PRICE", "TABLE_LIMIT_UP",
    # 缓存
    "CACHE_1MIN", "CACHE_5MIN", "CACHE_1HOUR", "CACHE_1DAY",
    # 系统
    "DEFAULT_TIMEOUT", "DEFAULT_RETRY", "DEFAULT_BATCH_SIZE",
    # SQL
    "SQL_STOCK_MAIN_GEM", "SQL_STOCK_MAIN_ONLY", "SQL_STOCK_ALL", "SQL_STOCK_EXCLUDE_LARGE",
    # 浏览器
    "FIREFOX_1408", "FIREFOX_1466", "FIREFOX_1509",
    "CHROME_1208", "DEFAULT_FIREFOX", "DEFAULT_CHROME",
    # 函数
    "get_market_by_code", "get_stock_type_by_code",
    "is_main_board", "is_gem", "is_star",
]
