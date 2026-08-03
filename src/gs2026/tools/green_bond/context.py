"""
绿名单共享数据上下文

一次性加载日行情 + 交易日历，供所有策略复用；
窗口指标（前1日/前2日等 lag）惰性计算一次，多模式共享，避免重复计算。
"""
import pandas as pd

from gs2026.tools.green_bond.calendar import TradingCalendar
from gs2026.utils import log_util

logger = log_util.setup_logger(__file__)


class GreenBondContext:
    """绿名单计算的共享上下文。

    Attributes:
        bond_daily: 日行情 DataFrame[code, trade_date, zgzf, stzf, ...]，含 trigger_date 列
        calendar: TradingCalendar 交易日历（提供 next_trade_date 映射）
        windowed: 窗口指标 DataFrame（惰性计算，含 prev1_*/prev2_* 等）
    """

    def __init__(self, bond_daily: pd.DataFrame, calendar_df: pd.DataFrame):
        df = bond_daily.copy()
        # trigger_date = 当日（触发条件的日期），策略统一输出它，框架据此映射 buy_date
        df["trigger_date"] = df["trade_date"]
        self.bond_daily = df
        self.calendar = TradingCalendar(calendar_df)
        self._windowed = None

    @property
    def windowed(self) -> pd.DataFrame:
        """惰性计算窗口指标（前1日/前2日 lag），多模式共享，只算一次。

        新增模式若需要更多 lag 指标（prev3、连板计数等），在此补充列。
        """
        if self._windowed is None:
            self._windowed = self._compute_window_metrics()
        return self._windowed

    def _compute_window_metrics(self) -> pd.DataFrame:
        """按 code 分组、date 升序，计算 lag 指标（对齐 Scala Window.lag）。"""
        df = self.bond_daily.sort_values(["code", "trade_date"]).copy()
        g = df.groupby("code", sort=False)
        # 前1日最高涨幅（model=1 若用 prev 口径可用；当前 model=1 用当日 zgzf）
        df["prev1_zgzf"] = g["zgzf"].shift(1)
        # 前1日/前2日实体涨幅（model=2 用）
        df["prev1_stzf"] = g["stzf"].shift(1)
        df["prev2_stzf"] = g["stzf"].shift(2)
        logger.info(f"窗口指标计算完成: {len(df)} 条")
        return df
