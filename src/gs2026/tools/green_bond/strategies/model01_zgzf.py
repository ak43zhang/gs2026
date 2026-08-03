"""
模式1：当日最高涨幅(zgzf) > 4

对齐 Scala GreenBondList filterCondition1：
  当日 zgzf > 4 即触发，buy_date = 当日的下一个交易日。
"""
from gs2026.tools.green_bond.base import GreenBondStrategy
from gs2026.tools.green_bond.registry import register


@register
class Model01Zgzf(GreenBondStrategy):
    model = "1"
    name = "当日最高涨幅>4"
    params = {"zgzf_threshold": 4.0}

    def evaluate(self, ctx):
        df = ctx.bond_daily
        threshold = self.params["zgzf_threshold"]
        hit = df[df["zgzf"] > threshold]
        return hit[["code", "trigger_date"]].copy()
