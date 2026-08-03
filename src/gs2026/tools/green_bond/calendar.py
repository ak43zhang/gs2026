"""
交易日历工具：批量 next_trade_date 映射

绿名单的 buy_date = 触发日的下一个交易日。
用交易日历（升序）构建 trade_date -> next_trade_date 的映射，
批量映射避免逐行查库（对齐 Scala 的 lead 窗口逻辑）。
"""
import pandas as pd

from gs2026.utils import log_util

logger = log_util.setup_logger(__file__)


class TradingCalendar:
    """交易日历：提供 next_trade_date 批量映射。"""

    def __init__(self, calendar_df: pd.DataFrame):
        """
        Args:
            calendar_df: DataFrame[trade_date]，升序（交易日）
        """
        cal = calendar_df.sort_values("trade_date").reset_index(drop=True)
        # 下一个交易日 = 向上移一位（对齐 Scala lead(trade_date, 1)）
        cal["next_trade_date"] = cal["trade_date"].shift(-1)
        self._next_map = dict(zip(cal["trade_date"], cal["next_trade_date"]))
        self._trade_dates = cal["trade_date"].tolist()

    def next_trade_date(self, d):
        """返回 d 的下一个交易日；无则返回 None（如最新交易日尚无下一日）。"""
        return self._next_map.get(d)

    def map_next(self, series: pd.Series) -> pd.Series:
        """批量映射：trigger_date Series -> buy_date Series。"""
        return series.map(self._next_map)

    @property
    def trade_dates(self) -> list:
        return self._trade_dates
