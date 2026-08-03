"""
绿名单生成主流程（编排 + CLI + 编程接口）

支持三种使用方式：

1. CLI 命令行（默认全量）：
   python -m gs2026.tools.green_bond.runner
   python -m gs2026.tools.green_bond.runner --mode incremental --start 2026-08-01 --end 2026-08-03

2. 编程方式 - 直接修改参数后执行：
   from gs2026.tools.green_bond.runner import run_with_params
   # 修改 model3 的参数
   run_with_params({
       "3": {"days_to_last_trade": 7, "trigger_progress": 0.8}  # 收紧参数
   })

3. 编程方式 - 完全自定义：
   from gs2026.tools.green_bond.runner import generate, override_strategy_params
   override_strategy_params("3", {"near_expiry_days": 30})  # 临时修改
   result = generate()  # 执行全量

流程：
  1. 加载日行情 + 交易日历
  2. 构建共享上下文
  3. 遍历所有已注册启用的策略，各自 evaluate 产出 [code, trigger_date]
  4. 合并所有模式，映射 buy_date（下一交易日）
  5. 去重（同 code+buy_date 取 model 最小，对齐 Scala）
  6. 落库（full 全量 / incremental 增量，唯一索引幂等 upsert）
"""
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import pandas as pd

from gs2026.tools.green_bond.context import GreenBondContext
from gs2026.tools.green_bond.repository import GreenBondRepository
from gs2026.tools.green_bond import registry
from gs2026.tools.green_bond import strategies  # noqa: F401 触发策略注册
from gs2026.utils import log_util

logger = log_util.setup_logger(__file__)

# 窗口指标最多回看的交易日数（prev2 需要向前 2 日，留足缓冲）
WINDOW_LOOKBACK_DAYS = 10


def override_strategy_params(model: str, params: Dict[str, Any]) -> bool:
    """在程序中临时修改指定策略的参数（不持久化，仅本次运行有效）。

    Args:
        model: 策略编号（如 "3"）
        params: 要覆盖的参数字典

    Returns:
        是否成功找到并修改

    示例：
        override_strategy_params("3", {"days_to_last_trade": 7, "near_expiry_days": 30})
    """
    strat = registry.get_strategy(model)
    if not strat:
        logger.warning(f"策略 {model} 未找到，无法修改参数")
        return False

    original = strat.params.copy()
    strat.params.update(params)
    logger.info(f"策略 {model}({strat.name}) 参数临时修改:")
    for k, v in params.items():
        logger.info(f"  {k}: {original.get(k)} -> {v}")
    return True


def reset_strategy_params(model: str) -> bool:
    """重置策略参数为原始默认值（通过重新实例化）。

    Args:
        model: 策略编号

    注意：这会重新创建策略实例，丢失之前的临时修改。
    """
    # 从注册表移除旧实例
    if model in registry._REGISTRY:
        old = registry._REGISTRY[model]
        del registry._REGISTRY[model]
        # 重新导入触发注册
        import importlib
        module_name = f"gs2026.tools.green_bond.strategies.model{int(model):02d}_"
        # 找到实际模块名
        for name in dir(strategies):
            if name.startswith(f"model{int(model):02d}_"):
                module = getattr(strategies, name)
                importlib.reload(module)
                logger.info(f"策略 {model} 已重置为默认参数")
                return True
    return False


def run_with_params(param_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
                   mode: str = "full",
                   start: str = None,
                   end: str = None) -> dict:
    """编程接口：先应用参数覆盖，再执行生成。

    Args:
        param_overrides: {model: {param: value}} 格式的参数覆盖
                         如 {"3": {"days_to_last_trade": 7}}
        mode: 'full' 或 'incremental'
        start/end: incremental 模式的日期范围

    Returns:
        生成结果字典

    示例：
        # 收紧 model3 的参数，然后执行
        result = run_with_params({
            "3": {
                "days_to_last_trade": 7,      # 从14天收紧到7天
                "trigger_progress": 0.8,        # 从67%收紧到80%
                "near_expiry_days": 30        # 从60天收紧到30天
            }
        })
        print(f"命中 {result['total']} 条")
    """
    if param_overrides:
        for model, params in param_overrides.items():
            override_strategy_params(model, params)

    return generate(mode=mode, start=start, end=end)


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
    logger.info(f"已注册启用模式: {[(s.model, s.name, s.params) for s in strats]}")
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
        logger.info(f"  模式 {strat.model}({strat.name}): {len(hits)} 条, 参数={strat.params}")

    if not parts:
        logger.warning("所有模式均无命中")
        merged = pd.DataFrame(columns=["code", "trigger_date", "model"])
    else:
        merged = pd.concat(parts, ignore_index=True)

    # 分离模式1/2和模式3
    merged_12 = merged[merged["model"].isin(["1", "2"])].copy()
    merged_3 = merged[merged["model"] == "3"].copy()

    # 模式1/2：映射 buy_date = trigger_date 的下一个交易日
    if not merged_12.empty:
        merged_12["buy_date"] = ctx.calendar.map_next(merged_12["trigger_date"])
        before = len(merged_12)
        merged_12 = merged_12[merged_12["buy_date"].notna()].copy()
        logger.info(f"模式1/2 映射 buy_date 后: {len(merged_12)} 条 (丢弃无下一交易日 {before - len(merged_12)} 条)")
    
    # 模式3：buy_date = 模式1/2的最新 buy_date（即今天）
    if not merged_3.empty:
        if not merged_12.empty:
            latest_buy_date = merged_12["buy_date"].max()
            merged_3["buy_date"] = latest_buy_date
            logger.info(f"模式3 buy_date = 模式1/2最新日期: {latest_buy_date}")
        else:
            # 模式1/2无数据，用今天的下一交易日（即明天）
            today_str = datetime.now().strftime("%Y-%m-%d")
            merged_3["buy_date"] = ctx.calendar.map_next([today_str] * len(merged_3))
            logger.info(f"模式1/2无数据，模式3 buy_date = 明天")

    # 合并回总表
    merged = pd.concat([merged_12, merged_3], ignore_index=True) if not merged_12.empty or not merged_3.empty else merged

    # 格式化 buy_date，不再去重（保留所有 model）
    if not merged.empty:
        merged["buy_date"] = pd.to_datetime(merged["buy_date"]).dt.strftime("%Y-%m-%d")
        dedup = merged[["code", "buy_date", "model"]].copy()
    else:
        dedup = merged

    # incremental：仅保留 buy_date ∈ [start, end]
    if mode == "incremental":
        dedup = dedup[(dedup["buy_date"] >= start) & (dedup["buy_date"] <= end)].copy()
        logger.info(f"增量过滤 buy_date ∈ [{start}, {end}]: {len(dedup)} 条")

    logger.info(f"最终待写入: {len(dedup)} 条")

    # 落库：按 _full_mode_behavior 分组处理
    if mode == "full":
        # 收集 rebuild 类型的 model（默认 rebuild）
        rebuild_models = []
        for strat in strats:
            behavior = strat.params.get("_full_mode_behavior", "rebuild")
            if behavior == "rebuild":
                rebuild_models.append(strat.model)
                logger.info(f"  模式 {strat.model}: rebuild 类型，将清空历史")
            else:
                logger.info(f"  模式 {strat.model}: {behavior} 类型，不清空")
        
        if rebuild_models:
            repo.delete_by_models(rebuild_models)
        # append 类型的 model 不清空，直接追加
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
                        help="full=全量重算; incremental=按 buy_date 范围增量 (默认: full)")
    parser.add_argument("--start", help="incremental 模式 buy_date 起始 YYYY-MM-DD")
    parser.add_argument("--end", help="incremental 模式 buy_date 结束 YYYY-MM-DD")
    args = parser.parse_args()
    generate(mode=args.mode, start=args.start, end=args.end)


if __name__ == "__main__":
    main()
