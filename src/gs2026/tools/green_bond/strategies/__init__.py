"""
策略包：导入所有策略模块以触发 @register 注册。

新增模式时，在此增加一行 import 即可。
"""
from gs2026.tools.green_bond.strategies import model01_zgzf   # noqa: F401
from gs2026.tools.green_bond.strategies import model02_stzf_sum  # noqa: F401
