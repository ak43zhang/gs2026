"""
模式2：前两日实体涨幅(stzf)之和 > 4，且两日均 > 0

对齐 Scala GreenBondList filterCondition2：
  当日判断 prev1_stzf + prev2_stzf > 4，且 prev1_stzf>0 且 prev2_stzf>0 即触发，
  buy_date = 当日的下一个交易日。
"""
from gs2026.tools.green_bond.base import GreenBondStrategy
from gs2026.tools.green_bond.registry import register


@register
class Model02StzfSum(GreenBondStrategy):
    model = "2"
    name = "前两日实体涨幅和>4且均>0"
    params = {"sum_threshold": 4.0, "min_each": 0.0}

    def evaluate(self, ctx):
        w = ctx.windowed
        p = self.params
        hit = w[
            (w["prev1_stzf"] > p["min_each"]) &
            (w["prev2_stzf"] > p["min_each"]) &
            ((w["prev1_stzf"] + w["prev2_stzf"]) > p["sum_threshold"])
        ]
        return hit[["code", "trigger_date"]].copy()
