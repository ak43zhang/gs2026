"""
华泰证券可转债半自动交易助手

本模块提供可转债交易的半自动化辅助功能：
- 接收量化系统的交易信号
- 自动准备委托单（填充代码、价格、数量）
- 人工最终确认后提交

重要声明：
1. 本系统不存储交易密码
2. 不自动提交订单（需人工点击确认）
3. 所有操作仅本地执行，不联网传输交易信息
4. 使用者需自行承担交易风险
"""

__version__ = "1.0.0"
__author__ = "GS2026"

from .trader import HuaTaiTrader
from .server import start_server

__all__ = ['HuaTaiTrader', 'start_server']
