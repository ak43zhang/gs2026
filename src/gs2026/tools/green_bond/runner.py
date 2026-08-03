"""
绿名单生成主流程（编排 + CLI）

流程：
  1. 加载日行情 + 交易日历
  2. 构建共享上下文
  3. 遍历所有已注册启用的策略，各自 evaluate 产出 [code, trigger_date]
  4. 合并所有模式，映射 buy_date（下一交易日）
  5. 去重（同 code+buy_date 取 model 最小，对齐 Scala）
  6. 落库（full 全量 / incremental 增量，唯一索引幂等 upsert）

运行：
  python -m gs2026.tools.green_bond.runner --mode full
  python -m gs2026.tools.green_bond.runner --mode incremental --start 2026-08-01 --end 2026-08-03
"""
import argparse
from datetime import datetime, timedelta

import pandas as pd

from gs2026.tools.green_bond.context import GreenBondContext
from gs2026.tools.green_bond.repository import GreenBondRepository
from gs2026.tools.green_bond import registry
from gs2026.tools.green_bond import strategies  # noqa: F401 触发策略注册
from gs2026.utils import log_util

logger = log_util.setup_logger(__file__)

# 窗口指标最多回看的交易日数（prev2 需要向前 2 日，留足缓冲）
WINDOW_LOOKBACK_DAYS = 10


def generate(mode: str = "full", start: str = None, end: str = None) -> dict:
    """生成绿名单主流程。

    Args:
        mode: 'full'（全量重算）| 'incremental'（按 buy_date 范围增量）
        start/end: incremental 模式的 buy_date 范围 'YYYY-MM-DD'

    Returns:
        结果统计字典
    """
    logger.info("=" * 70)
    logger.info(f"绿名单生成开始: mode={mode}, start={start}, end={end}")
    strats = registry.all_strategies()
    logger.info(f"已注册启用模式: {[(s.model, s.name) for s in strats]}")
    logger.info("=" * 70)

    repo = GreenBondRepository()
    # 确保表结构（唯一索引）
    repo.ensure_schema()

    # 数据加载范围：
    # - full: 全量（load_start=None）
    # - incremental: buy_date ∈ [start, end] → 触发日 ∈ [start 的上一交易日, end 的上一交易日]
    #   为算窗口指标(prev2)，行情还要再向前多取 WINDOW_LOOKBACK_DAYS 天
    load_start = None
    if mode == "incremental":
        if not start or not end:
            raise ValueError("incremental 模式必须指定 --start 和 --end")
        load_start = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=WINDOW_LOOKBACK_DAYS + 10)).strftime("%Y-%m-%d")

    bond_daily = repo.load_bond_daily(start=load_start, end=None)
    calendar_df = repo.load_calendar()

    if bond_daily.empty:
        logger.warning("日行情为空，终止")
        return {"success": False, "reason": "no bond daily data"}

    ctx = GreenBondContext(bond_daily, calendar_df)

    # 遍历策略产出
    parts = []
    for strat in strats:
        hits = strat.evaluate(ctx)
        if hits is None or hits.empty:
            logger.info(f"  模式 {strat.model}({strat.name}): 0 条")
            continue
        hits = hits[["code", "trigger_date"]].copy()
        hits["model"] = strat.model
        parts.append(hits)
        logger.info(f"  模式 {strat.model}({strat.name}): {len(hits)} 条")

    if not parts:
        logger.warning("所有模式均无命中")
        merged = pd.DataFrame(columns=["code", "trigger_date", "model"])
    else:
        merged = pd.concat(parts, ignore_index=True)

    # 映射 buy_date = trigger_date 的下一个交易日
    merged["buy_date"] = ctx.calendar.map_next(merged["trigger_date"])
    # 丢弃无下一交易日的（如最新交易日尚无 buy_date）
    before = len(merged)
    merged = merged[merged["buy_date"].notna()].copy()
    logger.info(f"映射 buy_date 后: {len(merged)} 条 (丢弃无下一交易日 {before - len(merged)} 条)")

    # 去重：同 code+buy_date 取 model 最小（对齐 Scala min(model)）
    if not merged.empty:
        merged["buy_date"] = pd.to_datetime(merged["buy_date"]).dt.strftime("%Y-%m-%d")
        dedup = (merged.sort_values("model")
                 .groupby(["code", "buy_date"], as_index=False)
                 .agg(model=("model", "min")))
    else:
        dedup = merged

    # incremental：仅保留 buy_date ∈ [start, end]
    if mode == "incremental":
        dedup = dedup[(dedup["buy_date"] >= start) & (dedup["buy_date"] <= end)].copy()
        logger.info(f"增量过滤 buy_date ∈ [{start}, {end}]: {len(dedup)} 条")

    logger.info(f"最终待写入: {len(dedup)} 条")

    # 落库
    if mode == "full":
        repo.delete_all()
    elif mode == "incremental":
        repo.delete_by_buy_date_range(start, end)

    rowcount = repo.upsert(dedup)

    result = {
        "success": True,
        "mode": mode,
        "total": len(dedup),
        "rowcount": rowcount,
        "by_model": dedup["model"].value_counts().to_dict() if not dedup.empty else {},
    }
    logger.info(f"绿名单生成完成: {result}")
    return result


def main():
    parser = argparse.ArgumentParser(description="债券绿名单生成")
    parser.add_argument("--mode", choices=["full", "incremental"], default="full",
                        help="full=全量重算; incremental=按 buy_date 范围增量")
    parser.add_argument("--start", help="incremental 模式 buy_date 起始 YYYY-MM-DD")
    parser.add_argument("--end", help="incremental 模式 buy_date 结束 YYYY-MM-DD")
    args = parser.parse_args()
    generate(mode=args.mode, start=args.start, end=args.end)


if __name__ == "__main__":
    main()
