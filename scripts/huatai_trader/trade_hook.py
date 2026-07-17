"""
交易Hook接口层 (trade_hook.py)
异常隔离: 所有异常内部消化,不影响主流程

用法:
    from trade_hook import TradeHook
    _trade_hook = TradeHook(config)
    
    # 命中时
    _trade_hook.on_hit(bond_code, bond_name, hit_price, scheme_detail, lots)
    
    # 每tick
    _trade_hook.on_tick(df_now)
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TradeHook:
    """
    交易Hook接口层
    
    职责:
    1. 异常隔离: 所有异常内部消化,不抛给调用方
    2. 开关控制: 支持动态启用/禁用
    3. 性能保障: 调用耗时<1ms,不阻塞主流程
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self._trader = None
        
        if self.enabled:
            try:
                from auto_trader import get_auto_trader
                self._trader = get_auto_trader(self.config)
                logger.info("[TradeHook] 初始化成功")
            except Exception as e:
                logger.error(f"[TradeHook] 初始化失败: {e}")
                self.enabled = False
    
    def on_hit(self, code: str, name: str, price: float, 
               scheme: Dict[str, Any], lots: int = 1):
        """
        命中时调用
        
        Args:
            code: 债券代码
            name: 债券名称
            price: 触发价格
            scheme: 方案详情
            lots: 手数
        """
        if not self.enabled:
            return
        
        try:
            if self._trader:
                self._trader.on_hit(code, name, price, scheme, lots)
        except Exception as e:
            # 异常内部消化,不影响主流程
            logger.debug(f"[TradeHook] on_hit异常: {e}")
    
    def on_tick(self, df_now):
        """
        每tick调用
        
        Args:
            df_now: 当前行情DataFrame
        """
        if not self.enabled:
            return
        
        try:
            if self._trader:
                self._trader.on_tick(df_now)
        except Exception as e:
            # 异常内部消化,不影响主流程
            logger.debug(f"[TradeHook] on_tick异常: {e}")
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """获取当前状态"""
        if not self.enabled or not self._trader:
            return None
        
        try:
            return self._trader.get_status()
        except Exception as e:
            logger.debug(f"[TradeHook] get_status异常: {e}")
            return None


# ==================== 便捷函数 ====================

# 全局Hook实例(单例)
_hook_instance: Optional[TradeHook] = None


def init_trade_hook(config: Dict[str, Any] = None) -> TradeHook:
    """初始化全局Hook实例"""
    global _hook_instance
    _hook_instance = TradeHook(config)
    return _hook_instance


def on_hit(code: str, name: str, price: float, 
           scheme: Dict[str, Any], lots: int = 1):
    """便捷函数: 命中时调用"""
    global _hook_instance
    if _hook_instance:
        _hook_instance.on_hit(code, name, price, scheme, lots)


def on_tick(df_now):
    """便捷函数: 每tick调用"""
    global _hook_instance
    if _hook_instance:
        _hook_instance.on_tick(df_now)


def get_status() -> Optional[Dict[str, Any]]:
    """便捷函数: 获取状态"""
    global _hook_instance
    if _hook_instance:
        return _hook_instance.get_status()
    return None
