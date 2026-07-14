"""
交易助手适配器 - 可插拔模块
用于 monitor_bond.py 中直接调用交易助手

特点：
- 完全可插拔：不影响原有功能
- 实时接入：在数据到达时立即处理
- 方案过滤：支持按方案名称过滤
- 通知方式：支持多种通知方式（弹窗、声音、企业微信等）

使用方法：
    from trader_adapter import TraderAdapter
    
    # 初始化（在monitor_bond.py启动时）
    trader = TraderAdapter()
    
    # 在命中检测后调用
    if hit_detected:
        trader.on_hit(bond_code, bond_name, price, scheme_name)
"""

import time
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List
import requests
import winsound

# 配置日志
logger = logging.getLogger(__name__)


class TraderAdapter:
    """
    交易助手适配器
    
    功能：
    1. 接收实时命中数据
    2. 按方案过滤
    3. 风控检查
    4. 调用交易助手HTTP服务
    5. 通知方式（弹窗、声音等）
    """
    
    # 默认配置
    DEFAULT_CONFIG = {
        # 是否启用
        'enabled': True,
        
        # 交易助手服务地址
        'trader_api_url': 'http://127.0.0.1:8081',
        
        # 请求超时（秒）
        'request_timeout': 35,
        
        # 允许触发的方案列表（为空表示全部）
        # 例如：['大盘债券斜率共振', '强势反弹']
        'allowed_schemes': [],
        
        # 禁止触发的方案列表
        'blocked_schemes': [],
        
        # 同一债券最小去抖间隔（秒）- 仅防止同一tick重复触发
        'min_interval_seconds': 10,  # 10秒去抖
        
        # 单日最大触发次数
        'max_daily_triggers': 50,
        
        # 单笔最大金额（元）
        'max_single_amount': 100000,
        
        # 单笔最小金额（元）
        'min_single_amount': 1000,
        
        # 价格有效范围
        'price_range': {'min': 50, 'max': 200},
        
        # 默认买入手数
        'default_lots': 1,
        
        # 通知方式配置
        'notifications': {
            # Windows弹窗通知
            'windows_toast': True,
            # 声音提示
            'sound': True,
            # 控制台日志
            'console': True,
        },
        
        # 交易时段（24小时制）
        'trading_hours': {
            'morning': {'start': '09:30', 'end': '11:30'},
            'afternoon': {'start': '13:00', 'end': '15:00'},
        },
    }
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化适配器
        
        Args:
            config: 自定义配置，会覆盖默认配置
        """
        self.config = self.DEFAULT_CONFIG.copy()
        if config:
            self._deep_update(self.config, config)
        
        # 状态记录
        self._triggered_cache: Dict[str, datetime] = {}  # 已触发缓存
        self._daily_count: int = 0  # 今日触发次数
        self._last_reset_date: str = datetime.now().strftime('%Y%m%d')  # 上次重置日期
        
        # 通知方式
        self._notifiers: List[Callable] = []
        self._setup_notifiers()
        
        # 检查是否启用
        if not self.config['enabled']:
            logger.info("[TraderAdapter] 交易助手适配器已禁用")
            return
        
        logger.info("[TraderAdapter] 交易助手适配器已初始化")
        logger.info(f"[TraderAdapter] 允许的方案: {self.config['allowed_schemes'] or '全部'}")
        logger.info(f"[TraderAdapter] 禁止的方案: {self.config['blocked_schemes'] or '无'}")
    
    def _deep_update(self, base: dict, update: dict):
        """深度更新字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
    def _setup_notifiers(self):
        """设置通知方式"""
        notif_config = self.config.get('notifications', {})
        
        if notif_config.get('sound'):
            self._notifiers.append(self._notify_sound)
        
        if notif_config.get('console'):
            self._notifiers.append(self._notify_console)
        
        if notif_config.get('windows_toast'):
            try:
                from win10toast import ToastNotifier
                self._toast = ToastNotifier()
                self._notifiers.append(self._notify_toast)
            except ImportError:
                logger.warning("[TraderAdapter] win10toast未安装，Windows通知不可用")
    
    # ==================== 通知方式 ====================
    
    def _notify_sound(self, title: str, message: str, success: bool = True):
        """声音通知"""
        try:
            if success:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                winsound.MessageBeep(winsound.MB_ICONHAND)
        except:
            pass
    
    def _notify_console(self, title: str, message: str, success: bool = True):
        """控制台通知"""
        status = "✓" if success else "✗"
        logger.info(f"[TraderAdapter] {status} {title}: {message}")
    
    def _notify_toast(self, title: str, message: str, success: bool = True):
        """Windows弹窗通知"""
        try:
            if hasattr(self, '_toast'):
                self._toast.show_toast(
                    title,
                    message,
                    duration=5,
                    threaded=True
                )
        except Exception as e:
            logger.warning(f"[TraderAdapter] Windows通知失败: {e}")
    
    def _send_notification(self, title: str, message: str, success: bool = True):
        """发送所有通知"""
        for notifier in self._notifiers:
            try:
                notifier(title, message, success)
            except Exception as e:
                logger.error(f"[TraderAdapter] 通知失败: {e}")
    
    # ==================== 核心方法 ====================
    
    def on_hit(self, bond_code: str, bond_name: str, price: float, 
               scheme_name: str, lots: int = None, **extra) -> bool:
        """
        命中回调 - 在检测到命中时调用
        
        Args:
            bond_code: 债券代码
            bond_name: 债券名称
            price: 触发价格
            scheme_name: 方案名称
            lots: 买入手数（默认从配置读取）
            **extra: 额外参数（预留）
            
        Returns:
            是否成功触发
        """
        # 检查是否启用
        if not self.config['enabled']:
            return False
        
        # 重置每日计数
        self._reset_daily_count_if_needed()
        
        # 1. 方案过滤检查
        if not self._check_scheme_filter(scheme_name):
            logger.debug(f"[TraderAdapter] 方案过滤跳过: {scheme_name}")
            return False
        
        # 2. 交易时段检查
        if not self._is_trading_time():
            logger.debug(f"[TraderAdapter] 非交易时段，跳过")
            return False
        
        # 3. 风控检查
        passed, reason = self._check_risk_limits(bond_code, price, lots)
        if not passed:
            logger.info(f"[TraderAdapter] 风控拦截: {reason}")
            self._send_notification("交易助手", f"风控拦截: {reason}", success=False)
            return False
        
        # 4. 调用交易助手
        lots = lots or self.config['default_lots']
        success, message = self._call_trader_api(bond_code, bond_name, price, lots)
        
        if success:
            # 更新状态
            self._update_trigger_status(bond_code)
            self._daily_count += 1
            
            # 发送通知
            self._send_notification(
                "交易助手 - 买入信号",
                f"{bond_name}({bond_code}) {lots}手 @ {price}元",
                success=True
            )
            logger.info(f"[TraderAdapter] 买入准备成功: {bond_code}")
        else:
            # 用户取消不视为错误
            if "用户取消" in message or "超时" in message:
                logger.info(f"[TraderAdapter] 用户取消或超时: {bond_code}")
            else:
                self._send_notification("交易助手失败", message, success=False)
                logger.error(f"[TraderAdapter] 买入准备失败: {message}")
        
        return success
    
    def _check_scheme_filter(self, scheme_name: str) -> bool:
        """检查方案过滤"""
        allowed = self.config.get('allowed_schemes', [])
        blocked = self.config.get('blocked_schemes', [])
        
        # 如果有允许列表，必须匹配
        if allowed and scheme_name not in allowed:
            return False
        
        # 如果在禁止列表，拒绝
        if blocked and scheme_name in blocked:
            return False
        
        return True
    
    def _is_trading_time(self) -> bool:
        """检查是否在交易时段"""
        now = datetime.now()
        current_time = now.strftime('%H:%M')
        
        hours = self.config.get('trading_hours', {})
        
        # 上午时段
        morning = hours.get('morning', {})
        if morning.get('start', '09:30') <= current_time <= morning.get('end', '11:30'):
            return True
        
        # 下午时段
        afternoon = hours.get('afternoon', {})
        if afternoon.get('start', '13:00') <= current_time <= afternoon.get('end', '15:00'):
            return True
        
        return False
    
    def _check_risk_limits(self, bond_code: str, price: float, lots: int) -> tuple:
        """
        风控检查
        
        Returns:
            (是否通过, 原因)
        """
        # 单日次数限制
        if self._daily_count >= self.config['max_daily_triggers']:
            return False, f"已达到单日最大触发次数({self.config['max_daily_triggers']})"
        
        # 金额检查
        lots = lots or self.config['default_lots']
        quantity = lots * 10  # 手数转张数
        amount = quantity * price
        
        if amount < self.config['min_single_amount']:
            return False, f"单笔金额({amount:.2f})低于最小限额"
        
        if amount > self.config['max_single_amount']:
            return False, f"单笔金额({amount:.2f})超过最大限额"
        
        # 价格范围检查
        price_range = self.config.get('price_range', {})
        if price < price_range.get('min', 50) or price > price_range.get('max', 200):
            return False, f"价格({price})超出有效范围"
        
        # 同一债券间隔检查（仅10秒去抖，防止同一tick重复）
        cache_key = f"{bond_code}_{datetime.now().strftime('%Y%m%d')}"
        if cache_key in self._triggered_cache:
            last_time = self._triggered_cache[cache_key]
            elapsed = (datetime.now() - last_time).total_seconds()
            min_interval = self.config['min_interval_seconds']
            if elapsed < min_interval:
                return False, f"去抖间隔内({min_interval}秒)，跳过"
        
        return True, "OK"
    
    def _call_trader_api(self, bond_code: str, bond_name: str, price: float, 
                         lots: int) -> tuple:
        """
        调用交易助手HTTP接口
        
        Returns:
            (是否成功, 消息)
        """
        try:
            url = f"{self.config['trader_api_url']}/api/prepare_buy"
            
            response = requests.post(
                url,
                json={
                    'code': bond_code,
                    'name': bond_name,
                    'price': price,
                    'lots': lots
                },
                timeout=self.config['request_timeout']
            )
            
            result = response.json()
            
            if result.get('success'):
                return True, result.get('message', '准备成功')
            else:
                return False, result.get('error', '准备失败')
                
        except requests.exceptions.Timeout:
            return False, "请求超时（用户可能未响应弹窗）"
        except requests.exceptions.ConnectionError:
            return False, "无法连接交易助手服务（请检查8081端口）"
        except Exception as e:
            return False, f"请求异常: {e}"
    
    def _update_trigger_status(self, bond_code: str):
        """更新触发状态"""
        cache_key = f"{bond_code}_{datetime.now().strftime('%Y%m%d')}"
        self._triggered_cache[cache_key] = datetime.now()
    
    def _reset_daily_count_if_needed(self):
        """检查并重置每日计数"""
        today = datetime.now().strftime('%Y%m%d')
        if today != self._last_reset_date:
            self._daily_count = 0
            self._last_reset_date = today
            self._triggered_cache.clear()
            logger.info(f"[TraderAdapter] 日期切换，计数器已重置")
    
    # ==================== 状态查询 ====================
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        self._reset_daily_count_if_needed()
        
        return {
            'enabled': self.config['enabled'],
            'is_trading_time': self._is_trading_time(),
            'daily_count': self._daily_count,
            'max_daily_triggers': self.config['max_daily_triggers'],
            'cached_triggers': len(self._triggered_cache),
            'config': {
                'allowed_schemes': self.config['allowed_schemes'],
                'blocked_schemes': self.config['blocked_schemes'],
            }
        }
    
    def reload_config(self, config: Dict[str, Any]):
        """重新加载配置"""
        self.config = self.DEFAULT_CONFIG.copy()
        self._deep_update(self.config, config)
        logger.info("[TraderAdapter] 配置已重新加载")


# ==================== 便捷函数 ====================

# 全局适配器实例（单例）
_trader_adapter: Optional[TraderAdapter] = None


def get_adapter(config: Dict[str, Any] = None) -> TraderAdapter:
    """获取适配器实例（单例模式）"""
    global _trader_adapter
    if _trader_adapter is None:
        _trader_adapter = TraderAdapter(config)
    return _trader_adapter


def on_hit(bond_code: str, bond_name: str, price: float, 
           scheme_name: str, lots: int = None, **extra) -> bool:
    """
    便捷函数 - 在monitor_bond.py中直接调用
    
    示例：
        from trader_adapter import on_hit
        
        if hit_detected:
            on_hit(bond_code, bond_name, price, scheme_name)
    """
    adapter = get_adapter()
    return adapter.on_hit(bond_code, bond_name, price, scheme_name, lots, **extra)


# 如果直接运行此文件，进行简单测试
if __name__ == '__main__':
    # 测试配置
    test_config = {
        'enabled': True,
        'allowed_schemes': ['测试方案'],
        'notifications': {
            'sound': True,
            'console': True,
        }
    }
    
    adapter = TraderAdapter(test_config)
    
    # 测试状态
    print("状态:", adapter.get_status())
    
    # 测试命中（需要交易助手服务运行）
    # result = adapter.on_hit('123257', '美诺转债', 105.20, '测试方案')
    # print("结果:", result)
