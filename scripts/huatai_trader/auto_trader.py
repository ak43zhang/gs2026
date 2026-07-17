"""
量化命中自动止盈止损 - 核心模块 (auto_trader.py)
状态机: IDLE → TRADING → MONITORING → IDLE

文档: 量化命中自动止盈止损-最终方案v7.md
"""

import time
import json
import logging
import threading
import winsound
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

@dataclass
class HitSignal:
    """命中信号"""
    code: str
    name: str
    buy_price: float
    tp_pct: float
    sl_pct: float
    max_hold_minutes: int
    quantity: int
    hit_time: float
    scheme_name: str = ""


@dataclass
class TradeState:
    """交易状态"""
    state: str = "IDLE"  # IDLE, TRADING, MONITORING
    current: Optional[HitSignal] = None
    hit_list: List[HitSignal] = None
    fill_time: Optional[float] = None
    tp_level: Optional[float] = None
    sl_level: Optional[float] = None
    max_hold_seconds: Optional[int] = None
    history: List[Dict] = None
    
    def __post_init__(self):
        if self.hit_list is None:
            self.hit_list = []
        if self.history is None:
            self.history = []


# ==================== 自动交易核心 ====================

class AutoTrader:
    """
    量化命中自动止盈止损核心
    
    状态机:
    IDLE ──→ TRADING ──→ MONITORING ──→ IDLE
                  │                        ↑
                  │ 30秒无弹窗              │ 止盈/止损/强平
                  ↓                        │
              撤单 → IDLE                  │
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get('enabled', True)
        self.signal_expire_seconds = config.get('signal_expire_seconds', 30)
        self.fill_timeout_seconds = config.get('fill_timeout_seconds', 30)
        self.popup_poll_ms = config.get('popup_poll_ms', 100)
        
        # 状态
        self._state = TradeState()
        self._lock = threading.RLock()
        
        # 交易线程
        self._trade_thread: Optional[threading.Thread] = None
        
        # 声音配置
        self.sounds = config.get('sounds', {})
        
        logger.info("[AutoTrader] 初始化完成")
    
    # ==================== 状态管理 ====================
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        with self._lock:
            current = self._state.current
            monitoring = None
            
            if self._state.state == "MONITORING" and current:
                hold_seconds = time.time() - (self._state.fill_time or 0)
                monitoring = {
                    'current_price': None,  # 由on_tick更新
                    'tp_level': self._state.tp_level,
                    'sl_level': self._state.sl_level,
                    'hold_seconds': int(hold_seconds),
                    'max_hold_seconds': self._state.max_hold_seconds,
                }
            
            return {
                'state': self._state.state,
                'hit_list': [asdict(h) for h in self._state.hit_list],
                'current': asdict(current) if current else None,
                'monitoring': monitoring,
                'history': self._state.history[-10:],  # 最近10条
            }
    
    # ==================== 阶段①: 命中收集 ====================
    
    def on_hit(self, code: str, name: str, price: float, 
               scheme_detail: Dict, lots: int = 1):
        """
        monitor_bond每tick调用, 非阻塞(<1ms)
        
        Args:
            code: 债券代码
            name: 债券名称
            price: 触发价格
            scheme_detail: 方案详情
            lots: 手数
        """
        if not self.enabled:
            return
        
        with self._lock:
            # 非IDLE状态不收新命中
            if self._state.state != "IDLE":
                logger.debug(f"[AutoTrader] {self._state.state}状态, 忽略命中: {code}")
                return
            
            # 计算买入价(根据offset_mode)
            offset_mode = scheme_detail.get('offset_mode', 'fixed')
            price_offset = scheme_detail.get('price_offset', 0)
            if offset_mode == 'percent':
                buy_price = price * (1 + price_offset / 100)
            else:
                buy_price = price + price_offset
            
            hit = HitSignal(
                code=code,
                name=name,
                buy_price=round(buy_price, 3),
                tp_pct=scheme_detail.get('take_profit', 3.0),
                sl_pct=scheme_detail.get('stop_loss', 2.0),
                max_hold_minutes=scheme_detail.get('max_hold_time', 30),
                quantity=lots * 10,
                hit_time=time.time(),
                scheme_name=scheme_detail.get('name', ''),
            )
            
            # 检查是否已存在
            if any(h.code == code for h in self._state.hit_list):
                logger.debug(f"[AutoTrader] 已存在: {code}")
                return
            
            self._state.hit_list.append(hit)
            logger.info(f"[AutoTrader] 新命中: {code} {name} @ {hit.buy_price}")
            self._play_sound('hit')
            
            # 清理过期信号
            self._cleanup_expired_hits()
    
    def _cleanup_expired_hits(self):
        """清理过期命中信号"""
        now = time.time()
        expired = [h for h in self._state.hit_list 
                   if now - h.hit_time >= self.signal_expire_seconds]
        for h in expired:
            logger.info(f"[AutoTrader] 命中过期: {h.code}")
        self._state.hit_list = [h for h in self._state.hit_list 
                                if now - h.hit_time < self.signal_expire_seconds]
    
    # ==================== 阶段②: 用户选择买入 ====================
    
    def on_buy_click(self, code: str) -> Dict[str, Any]:
        """
        前端点[买]触发(API调用)
        
        Args:
            code: 债券代码
            
        Returns:
            操作结果
        """
        if not self.enabled:
            return {'success': False, 'message': '功能未启用'}
        
        with self._lock:
            if self._state.state != "IDLE":
                return {'success': False, 'message': f'当前状态: {self._state.state}'}
            
            # 从列表找到这条命中
            hit = next((h for h in self._state.hit_list if h.code == code), None)
            if not hit:
                return {'success': False, 'message': '信号已过期或不存在'}
            
            # 进入交易状态
            self._state.state = "TRADING"
            self._state.current = hit
            self._state.hit_list = []  # 清空列表(本轮结束)
            
            logger.info(f"[AutoTrader] 开始交易: {code}")
            
            # 启动交易线程
            self._trade_thread = threading.Thread(
                target=self._trade_thread_worker,
                args=(hit,),
                daemon=True
            )
            self._trade_thread.start()
            
            return {'success': True, 'message': f'开始交易 {code}'}
    
    # ==================== 阶段③: 交易线程 ====================
    
    def _trade_thread_worker(self, hit: HitSignal):
        """
        独立线程: 填表→等弹窗→设TP/SL或撤单
        
        Args:
            hit: 命中信号
        """
        try:
            # 1. 填充买入表单
            self._fill_buy_form(hit)
            self._play_sound('filled')
            
            # 2. 等待成交弹窗(30秒)
            filled = self._wait_for_fill_popup(hit.code, self.fill_timeout_seconds)
            
            if filled:
                # === 路径A: 买到了 ===
                self._on_filled(hit)
            else:
                # === 路径B: 没买到 ===
                self._on_not_filled(hit)
                
        except Exception as e:
            logger.error(f"[AutoTrader] 交易线程异常: {e}", exc_info=True)
            self._end_trade('error', str(e))
    
    def _fill_buy_form(self, hit: HitSignal):
        """填充买入表单"""
        logger.info(f"[AutoTrader] 填充买入: {hit.code} @ {hit.buy_price}")
        
        # TODO: 调用trader.py的prepare_buy_order
        # 这里简化处理,实际应调用HTTP API或直接使用trader
        try:
            import requests
            resp = requests.post(
                'http://127.0.0.1:8081/api/prepare_buy',
                json={
                    'code': hit.code,
                    'name': hit.name,
                    'price': hit.buy_price,
                    'lots': hit.quantity // 10,
                },
                timeout=5
            )
            logger.info(f"[AutoTrader] 买入填充结果: {resp.json()}")
        except Exception as e:
            logger.warning(f"[AutoTrader] 买入填充失败: {e}")
            raise
    
    def _wait_for_fill_popup(self, code: str, timeout: int) -> bool:
        """
        等待成交弹窗
        
        Args:
            code: 债券代码
            timeout: 超时秒数
            
        Returns:
            是否检测到成交
        """
        logger.info(f"[AutoTrader] 等待成交弹窗: {code}, 超时{timeout}秒")
        
        # 使用极简方案检测成交弹窗: 检测到右下角新Afx窗口即认为成交
        try:
            import ctypes
            import ctypes.wintypes
            from ctypes import windll, byref, WINFUNCTYPE
            
            # 监控区域 - 屏幕右下角
            MONITOR_REGION = {
                'x_min': 1400, 'x_max': 1920,
                'y_min': 750, 'y_max': 1250,
            }
            
            def get_window_rect(hwnd):
                rect = ctypes.wintypes.RECT()
                windll.user32.GetWindowRect(hwnd, byref(rect))
                return rect.left, rect.top, rect.right, rect.bottom
            
            def is_in_region(hwnd):
                left, top, right, bottom = get_window_rect(hwnd)
                center_x = (left + right) // 2
                center_y = (top + bottom) // 2
                return (MONITOR_REGION['x_min'] <= center_x <= MONITOR_REGION['x_max'] and
                        MONITOR_REGION['y_min'] <= center_y <= MONITOR_REGION['y_max'])
            
            def get_window_class(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                windll.user32.GetClassNameW(hwnd, buf, 256)
                return buf.value
            
            def is_visible(hwnd):
                return bool(windll.user32.IsWindowVisible(hwnd))
            
            def enum_windows():
                windows = []
                @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                def cb(hwnd, lp):
                    if is_visible(hwnd) and is_in_region(hwnd):
                        windows.append(hwnd)
                    return True
                windll.user32.EnumWindows(cb, 0)
                return windows
            
            # 记录基准
            logger.debug("[AutoTrader] 记录基准状态...")
            hwnds = enum_windows()
            baseline = set()
            for hwnd in hwnds:
                cls = get_window_class(hwnd)
                if cls.startswith("Afx:"):
                    baseline.add(hwnd)
            logger.debug(f"[AutoTrader] 基准Afx窗口: {len(baseline)}个")
            
            start = time.time()
            
            while time.time() - start < timeout:
                # 获取当前
                hwnds = enum_windows()
                current = set()
                for hwnd in hwnds:
                    cls = get_window_class(hwnd)
                    if cls.startswith("Afx:"):
                        current.add(hwnd)
                
                # 新窗口
                new_hwnds = current - baseline
                
                for hwnd in new_hwnds:
                    cls = get_window_class(hwnd)
                    left, top, right, bottom = get_window_rect(hwnd)
                    width = right - left
                    height = bottom - top
                    
                    # 检查大小 (365x167 左右)
                    if 300 < width < 450 and 120 < height < 250:
                        logger.info(f"[AutoTrader] 检测到成交弹窗 (句柄={hwnd}, 类名={cls[:30]}...)")
                        logger.info(f"[AutoTrader] 成交确认: {code}")
                        
                        # 自动关闭弹窗
                        try:
                            from pywinauto import Desktop
                            desktop = Desktop(backend="uia")
                            window = desktop.window(handle=hwnd)
                            ok_btn = window.child_window(title="确定", control_type="Button")
                            if ok_btn.exists(timeout=0.5):
                                ok_btn.click()
                                logger.debug("[AutoTrader] 已关闭弹窗")
                        except:
                            pass
                        
                        return True
                
                # 更新基准
                baseline.update(current)
                time.sleep(self.popup_poll_ms / 1000)
            
            logger.warning(f"[AutoTrader] 等待成交弹窗超时: {code}")
            return False
            
        except Exception as e:
            logger.error(f"[AutoTrader] 弹窗检测失败: {e}")
            return False
    
    def _on_filled(self, hit: HitSignal):
        """成交后的处理"""
        logger.info(f"[AutoTrader] 成交: {hit.code}")
        self._play_sound('filled')
        
        # 计算止盈止损价位
        tp_level = hit.buy_price * (1 + hit.tp_pct / 100)
        sl_level = hit.buy_price * (1 - hit.sl_pct / 100)
        
        # 设置止盈止损
        result = self._place_tp_sl(hit, tp_level, sl_level)
        
        if result:
            self._play_sound('tp_sl_set')
        else:
            self._play_sound('error')
            logger.warning(f"[AutoTrader] 止盈止损设置失败: {hit.code}")
        
        # 进入持仓监控状态
        with self._lock:
            self._state.fill_time = time.time()
            self._state.tp_level = round(tp_level, 3)
            self._state.sl_level = round(sl_level, 3)
            self._state.max_hold_seconds = hit.max_hold_minutes * 60
            self._state.state = "MONITORING"
        
        logger.info(f"[AutoTrader] 进入监控: {hit.code} TP={tp_level:.3f} SL={sl_level:.3f}")
    
    def _place_tp_sl(self, hit: HitSignal, tp_level: float, sl_level: float) -> bool:
        """
        设置止盈止损
        
        Args:
            hit: 命中信号
            tp_level: 止盈价位
            sl_level: 止损价位
            
        Returns:
            是否成功
        """
        logger.info(f"[AutoTrader] 设置止盈止损: {hit.code} TP={tp_level:.3f} SL={sl_level:.3f}")
        
        # TODO: 调用TpSlPlacer
        # 这里简化处理,实际应调用trade_flow.py中的TpSlPlacer
        try:
            # 尝试使用现有的TpSlPlacer
            from trade_flow import get_trade_flow_manager
            manager = get_trade_flow_manager()
            if manager.tp_sl_placer:
                result = manager.tp_sl_placer.place(
                    bond_code=hit.code,
                    base_price=hit.buy_price,
                    tp_pct=hit.tp_pct,
                    sl_pct=hit.sl_pct,
                    quantity=hit.quantity,
                )
                return result.get('success', False)
        except Exception as e:
            logger.warning(f"[AutoTrader] 设置止盈止损失败: {e}")
        
        return False
    
    def _on_not_filled(self, hit: HitSignal):
        """未成交的处理"""
        logger.info(f"[AutoTrader] 未成交,尝试撤单: {hit.code}")
        
        # 尝试撤单
        cancelled = self._try_cancel_order(hit.code)
        
        if cancelled:
            logger.info(f"[AutoTrader] 撤单成功: {hit.code}")
            self._play_sound('timeout')
            self._end_trade('timeout_cancelled')
        else:
            # 撤不掉(可能已成交但弹窗漏了)
            logger.warning(f"[AutoTrader] 撤单失败,可能已成交: {hit.code}")
            self._play_sound('alert')
            self._end_trade('alert_check_manually')
    
    def _try_cancel_order(self, code: str) -> bool:
        """
        尝试撤单
        
        Args:
            code: 债券代码
            
        Returns:
            是否成功撤单
        """
        logger.info(f"[AutoTrader] 尝试撤单: {code}")
        
        # TODO: 实现撤单功能
        # 需要知道F3撤单的操作细节
        # 方案1: 按F3打开撤单列表,找到对应code,点击撤单
        # 方案2: 如果有委托编号,直接调用API撤单
        
        return False
    
    # ==================== 阶段④: 持仓监控 ====================
    
    def on_tick(self, df_now):
        """
        monitor_bond每tick调用,传入当前行情
        
        Args:
            df_now: 当前行情DataFrame
        """
        if not self.enabled:
            return
        
        with self._lock:
            if self._state.state != "MONITORING":
                return
            
            hit = self._state.current
            if not hit:
                return
            
            # 获取当前价格
            price = self._get_price(df_now, hit.code)
            if price is None:
                return
            
            # 更新监控数据
            # (这里可以存储当前价格用于前端展示)
            
            # 止盈触发
            if price >= self._state.tp_level:
                logger.info(f"[AutoTrader] 止盈触发: {hit.code} @ {price}")
                self._play_sound('tp_triggered')
                self._end_trade('take_profit', price)
                return
            
            # 止损触发
            if price <= self._state.sl_level:
                logger.info(f"[AutoTrader] 止损触发: {hit.code} @ {price}")
                self._play_sound('sl_triggered')
                self._end_trade('stop_loss', price)
                return
            
            # 持仓超时 → 强平
            hold_seconds = time.time() - self._state.fill_time
            if hold_seconds >= self._state.max_hold_seconds:
                logger.info(f"[AutoTrader] 持仓超时,强平: {hit.code}")
                self._force_sell(hit, price)
    
    def _get_price(self, df_now, code: str) -> Optional[float]:
        """从DataFrame获取指定代码的当前价格"""
        try:
            row = df_now[df_now['bond_code'] == code]
            if len(row) > 0:
                return float(row['price'].iloc[0])
        except Exception as e:
            logger.debug(f"[AutoTrader] 获取价格失败: {code}, {e}")
        return None
    
    def _force_sell(self, hit: HitSignal, price: float):
        """
        持仓超时强平: 填充卖出表单
        
        Args:
            hit: 命中信号
            price: 当前价格
        """
        logger.info(f"[AutoTrader] 强平卖出: {hit.code} @ {price}")
        
        def _do_sell():
            try:
                # TODO: 调用卖出填充
                import requests
                resp = requests.post(
                    'http://127.0.0.1:8081/api/prepare_sell',
                    json={
                        'code': hit.code,
                        'name': hit.name,
                        'price': price,
                        'lots': hit.quantity // 10,
                    },
                    timeout=5
                )
                logger.info(f"[AutoTrader] 强平填充结果: {resp.json()}")
                self._play_sound('force_sell')
                self._end_trade('force_sell', price)
            except Exception as e:
                logger.error(f"[AutoTrader] 强平失败: {e}")
                self._end_trade('force_sell_failed', price)
        
        threading.Thread(target=_do_sell, daemon=True).start()
    
    # ==================== 统一结束 ====================
    
    def _end_trade(self, reason: str, price: Optional[float] = None):
        """
        所有路径的统一结束点
        
        Args:
            reason: 结束原因
            price: 结束时的价格(可选)
        """
        with self._lock:
            hit = self._state.current
            if not hit:
                return
            
            # 记录到历史
            record = {
                'code': hit.code,
                'name': hit.name,
                'buy_price': hit.buy_price,
                'exit_price': price,
                'reason': reason,
                'time': datetime.now().isoformat(),
            }
            self._state.history.append(record)
            
            # 记录日志
            profit_pct = None
            if price:
                profit_pct = (price - hit.buy_price) / hit.buy_price * 100
            
            logger.info(f"[AutoTrader] 交易结束: {hit.code} 原因={reason} 盈亏={profit_pct:.2f}%" if profit_pct else f"[AutoTrader] 交易结束: {hit.code} 原因={reason}")
            
            # 清空状态
            self._state.current = None
            self._state.hit_list = []
            self._state.state = "IDLE"
            self._state.fill_time = None
            self._state.tp_level = None
            self._state.sl_level = None
            self._state.max_hold_seconds = None
        
        # 提醒
        self._play_sound('trade_end')
    
    # ==================== 声音提示 ====================
    
    def _play_sound(self, sound_type: str):
        """播放提示音"""
        if not self.sounds.get('enabled', True):
            return
        
        try:
            sound_file = self.sounds.get(sound_type)
            if sound_file and Path(sound_file).exists():
                # 播放自定义音频
                import ctypes
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW('close notify_sound', None, 0, 0)
                winmm.mciSendStringW(f'open "{sound_file}" type mpegvideo alias notify_sound', None, 0, 0)
                winmm.mciSendStringW('play notify_sound', None, 0, 0)
            else:
                # 系统默认音
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as e:
            logger.debug(f"[AutoTrader] 播放声音失败: {e}")


# ==================== 全局单例 ====================

_auto_trader: Optional[AutoTrader] = None


def get_auto_trader(config: Dict[str, Any] = None) -> AutoTrader:
    """获取AutoTrader单例"""
    global _auto_trader
    if _auto_trader is None:
        if config is None:
            # 默认配置
            config = {
                'enabled': True,
                'signal_expire_seconds': 30,
                'fill_timeout_seconds': 30,
                'popup_poll_ms': 100,
                'sounds': {
                    'enabled': True,
                },
            }
        _auto_trader = AutoTrader(config)
    return _auto_trader
