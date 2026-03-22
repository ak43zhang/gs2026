"""
pandas配置初始化
在模块级别检查是否是第一次导入
"""
import sys
from typing import NoReturn

import pandas as pd

if not hasattr(sys.modules[__name__], '_initialized'):
    # 第一次导入时执行设置
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.expand_frame_repr', False)
    pd.set_option('display.unicode.ambiguous_as_wide', True)
    pd.set_option('display.unicode.east_asian_width', True)
    pd.set_option('mode.chained_assignment', None)

    print("Pandas显示选项已全局设置。")
    sys.modules[__name__]._initialized = True


def set_pandas_display_options() -> NoReturn:
    """
    向后兼容的函数，实际上配置在导入时已经完成
    """
    pass
