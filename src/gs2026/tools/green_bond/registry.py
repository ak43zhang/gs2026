"""
绿名单模式策略注册表

通过 @register 装饰器注册策略，runner 遍历所有已注册且启用的策略执行。
新增模式只需新建策略文件 + @register + 在 strategies/__init__.py 导入，零改动主流程。
"""
from typing import Dict, List

from gs2026.tools.green_bond.base import GreenBondStrategy
from gs2026.utils import log_util

logger = log_util.setup_logger(__file__)

# model -> 策略实例
_REGISTRY: Dict[str, GreenBondStrategy] = {}


def register(strategy_cls):
    """类装饰器：注册一个绿名单策略。

    - 校验 model 非空且全局唯一
    - 实例化并存入注册表
    """
    inst = strategy_cls()
    if not inst.model:
        raise ValueError(f"策略 {strategy_cls.__name__} 未设置 model 编号")
    if inst.model in _REGISTRY:
        existed = _REGISTRY[inst.model].__class__.__name__
        raise ValueError(
            f"重复的 model 编号 '{inst.model}': {strategy_cls.__name__} 与 {existed} 冲突"
        )
    _REGISTRY[inst.model] = inst
    logger.info(f"注册绿名单模式: model={inst.model} name={inst.name} enabled={inst.enabled}")
    return strategy_cls


def all_strategies(include_disabled: bool = False) -> List[GreenBondStrategy]:
    """返回所有已注册策略。

    Args:
        include_disabled: 是否包含 enabled=False 的策略（默认只返回启用的）
    """
    strategies = list(_REGISTRY.values())
    if not include_disabled:
        strategies = [s for s in strategies if s.enabled]
    # 按 model 排序，保证输出稳定
    return sorted(strategies, key=lambda s: s.model)


def get_strategy(model: str) -> GreenBondStrategy:
    """按 model 编号获取策略实例。"""
    return _REGISTRY.get(model)


def clear_registry():
    """清空注册表（仅测试用）。"""
    _REGISTRY.clear()
