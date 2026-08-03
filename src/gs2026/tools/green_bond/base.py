"""
绿名单模式策略基类

每个绿名单模式实现一个 GreenBondStrategy 子类，通过 @register 注册。
策略只负责"判定"：输入共享上下文，输出满足本模式的 [code, trigger_date] 记录。
buy_date（下一交易日）由框架统一映射，落库由框架统一负责。
"""
from abc import ABC, abstractmethod
import pandas as pd


class GreenBondStrategy(ABC):
    """绿名单模式策略基类。

    子类必须：
      - 设置类属性 model（字符串，全局唯一，写入 green_bond_list.model）
      - 实现 evaluate(ctx) -> DataFrame[code, trigger_date]

    可选：
      - name: 模式名称/描述
      - params: 阈值等参数字典
      - enabled: 是否启用（默认 True；软下线设为 False）
    """

    model: str = None          # 模式编号（唯一，字符串）
    name: str = ""             # 模式名称
    params: dict = {}          # 阈值等参数
    enabled: bool = True       # 是否启用（软下线开关）

    @abstractmethod
    def evaluate(self, ctx) -> pd.DataFrame:
        """判定满足本模式的记录。

        Args:
            ctx: GreenBondContext，含共享日行情/窗口指标/交易日历

        Returns:
            DataFrame，必须包含两列：
              - code (str): 债券代码
              - trigger_date: 触发条件的当日（date/字符串），框架据此映射 buy_date
        """
        raise NotImplementedError

    def __repr__(self):
        return f"<GreenBondStrategy model={self.model} name={self.name} enabled={self.enabled}>"
