"""
绿名单一致性验收脚本

比对新系统产出 vs 现有 green_bond_list 表数据：
  - 以 (code, buy_date, model) 三元组为键做集合比对
  - 输出：只在旧 / 只在新 / 交集 的数量，及差异样本

用法：
  python -m gs2026.tools.green_bond.verify              # 全量比对（不写库，仅计算对比）
  python -m gs2026.tools.green_bond.verify --snapshot   # 先快照现有表为基线再比对
"""
import argparse

import pandas as pd

from gs2026.tools.green_bond.context import GreenBondContext
from gs2026.tools.green_bond.repository import GreenBondRepository
from gs2026.tools.green_bond import registry
from gs2026.tools.green_bond import strategies  # noqa: F401
from gs2026.utils import log_util

logger = log_util.setup_logger(__file__)


def _compute_new_result() -> pd.DataFrame:
    """跑一遍计算逻辑，返回 [code, buy_date, model]（不写库）。"""
    repo = GreenBondRepository()
    bond_daily = repo.load_bond_daily()
    calendar_df = repo.load_calendar()
    ctx = GreenBondContext(bond_daily, calendar_df)

    parts = []
    for strat in registry.all_strategies():
        hits = strat.evaluate(ctx)
        if hits is None or hits.empty:
            continue
        hits = hits[["code", "trigger_date"]].copy()
        hits["model"] = strat.model
        parts.append(hits)

    if not parts:
        return pd.DataFrame(columns=["code", "buy_date", "model"])

    merged = pd.concat(parts, ignore_index=True)
    merged["buy_date"] = ctx.calendar.map_next(merged["trigger_date"])
    merged = merged[merged["buy_date"].notna()].copy()
    merged["buy_date"] = pd.to_datetime(merged["buy_date"]).dt.strftime("%Y-%m-%d")
    merged["code"] = merged["code"].astype(str).str.strip()
    dedup = (merged.sort_values("model")
             .groupby(["code", "buy_date"], as_index=False)
             .agg(model=("model", "min")))
    return dedup


def verify(snapshot: bool = False) -> dict:
    repo = GreenBondRepository()
    if snapshot:
        repo.snapshot_baseline()

    old = repo.load_existing()
    new = _compute_new_result()

    logger.info(f"现有表记录: {len(old)} 条")
    logger.info(f"新系统产出: {len(new)} 条")

    # 三元组集合
    def _keyset(df):
        if df.empty:
            return set()
        return set(zip(df["code"], df["buy_date"], df["model"]))

    old_set = _keyset(old)
    new_set = _keyset(new)

    only_old = old_set - new_set
    only_new = new_set - old_set
    inter = old_set & new_set

    logger.info("=" * 60)
    logger.info(f"交集(一致): {len(inter)} 条")
    logger.info(f"只在旧(新系统未产出): {len(only_old)} 条")
    logger.info(f"只在新(新系统多出): {len(only_new)} 条")
    logger.info("=" * 60)

    def _sample(s, n=20):
        return sorted(list(s))[:n]

    logger.info(f"只在旧 样本: {_sample(only_old)}")
    logger.info(f"只在新 样本: {_sample(only_new)}")

    # 按 buy_date 分布看差异集中在哪
    if only_old:
        od = pd.DataFrame(list(only_old), columns=["code", "buy_date", "model"])
        logger.info(f"只在旧 - buy_date 分布(前10):\n{od['buy_date'].value_counts().head(10)}")
    if only_new:
        nd = pd.DataFrame(list(only_new), columns=["code", "buy_date", "model"])
        logger.info(f"只在新 - buy_date 分布(前10):\n{nd['buy_date'].value_counts().head(10)}")

    consistent = (len(only_old) == 0 and len(only_new) == 0)
    logger.info(f"\n{'✅ 逻辑完全一致' if consistent else '⚠️ 存在差异，需分析原因'}")

    return {
        "old_count": len(old),
        "new_count": len(new),
        "intersection": len(inter),
        "only_old": len(only_old),
        "only_new": len(only_new),
        "consistent": consistent,
    }


def main():
    parser = argparse.ArgumentParser(description="绿名单一致性验收")
    parser.add_argument("--snapshot", action="store_true", help="先快照现有表为基线")
    args = parser.parse_args()
    verify(snapshot=args.snapshot)


if __name__ == "__main__":
    main()
