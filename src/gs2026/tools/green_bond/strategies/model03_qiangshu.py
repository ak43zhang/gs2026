"""
模式3：强赎预警债券（离强赎日期近或已过强赎期）

数据源: data_bond_qs_jsl（集思录强赎数据）
判定条件（满足任一即入名单，业界宽松标准）：
  A. 已公告强赎且最后交易日距今≤14天（含已过期）
  B. 强赎天计数进度≥67%（即10/15，触发条件满足2/3）
  C. 债券到期日距今≤60天（临近到期，公司可能强赎促转股）

参数设定原因（业界标准+宽松）：
  - days_to_last_trade=14: 两周预警期，给投资者充足时间应对，非紧急7天
  - trigger_progress=0.67: 强赎条件满足2/3即预警（10/15天），而非80%或100%
  - near_expiry_days=60: 两个月到期预警，覆盖回售期前窗口，非严格30天

buy_date: 名单生成日的下一个交易日（与model1/2保持一致语义）
"""
import re
from datetime import datetime, timedelta

import pandas as pd

from gs2026.tools.green_bond.base import GreenBondStrategy
from gs2026.tools.green_bond.registry import register


@register
class Model03Qiangshu(GreenBondStrategy):
    model = "3"
    name = "强赎预警（已公告/天计数高/临近到期）"
    params = {
        "announced_status": ["已公告强赎"],
        "days_to_last_trade": 14,      # 两周预警期（宽松）
        "trigger_progress": 0.67,      # 2/3进度即预警（10/15）
        "near_expiry_days": 60,        # 两个月到期预警（宽松）
    }

    def evaluate(self, ctx):
        # 从 repository 读取强赎数据（通过 context 扩展或直接从 repo 读）
        # 这里直接从 MySQL 读取 data_bond_qs_jsl
        from gs2026.tools.green_bond.repository import GreenBondRepository
        repo = GreenBondRepository()
        df = repo.load_qs_jsl()
        if df.empty:
            return pd.DataFrame(columns=["code", "trigger_date"])

        today = datetime.now().date()
        p = self.params

        # 条件A：已公告强赎 + 最后交易日距今≤14天
        cond_a = pd.Series(False, index=df.index)
        if p["announced_status"]:
            status_match = df["强赎状态"].isin(p["announced_status"])
            # 最后交易日距今天数（NULL视为无穷远，已过期为负数）
            days_to_last = (df["最后交易日"] - pd.Timestamp(today)).dt.days
            days_match = days_to_last <= p["days_to_last_trade"]  # 含NULL(无穷大)不满足，含已过期(负数)满足
            cond_a = status_match & days_match.fillna(False)

        # 条件B：强赎天计数进度≥67%
        cond_b = df["强赎进度"] >= p["trigger_progress"]

        # 条件C：到期日距今≤60天
        days_to_expiry = (df["到期日"] - pd.Timestamp(today)).dt.days
        cond_c = days_to_expiry <= p["near_expiry_days"]

        hit = df[cond_a | cond_b | cond_c].copy()
        if hit.empty:
            return pd.DataFrame(columns=["code", "trigger_date"])

        hit["trigger_date"] = today
        return hit[["code", "trigger_date"]].copy()
