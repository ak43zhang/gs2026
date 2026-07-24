"""
交易流程管理器 v2 - Web面板版
状态机: CREATED → WAIT_BUY → CONFIRMING → FILLED → TP_SL_SET

monitor_bond.py 调用接口:
    from trade_flow import get_trade_flow_manager
    manager = get_trade_flow_manager()
    manager.on_hit(bond_code, bond_name, hit_price, scheme_detail, lots)
"""

import time
import json
import logging
import threading
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

@dataclass
class TradeOrder:
    order_id: str
    bond_code: str
    bond_name: str
    scheme_name: str
    hit_price: float
    price_offset: float
    offset_mode: str
    target_buy_price: float
    tp_pct: float
    sl_pct: float
    lots: int = 1
    quantity: int = 10
    status: str = "created"
    created_at: str = ""
    bought_at: str = ""        # 用户点了"已买入"的时间
    confirmed_at: str = ""     # 确认成交时间
    tp_sl_set_at: str = ""
    error_msg: str = ""


# ==================== 止盈止损提交器(纯Win32 API) ====================

class TpSlPlacer:
    """已验证的止盈止损条件单自动化"""

    XIADAN_TITLE = "网上股票交易系统5.0"
    POPUP_TITLE = "华泰理财通"
    POPUP_CLASS = "Chrome_WidgetWin_1"
    MAX_RETRIES = 3
    RETRY_INTERVAL = 2

    def __init__(self, positions_file: str):
        self.positions = self._load_positions(positions_file)

    def place(self, bond_code, base_price, tp_pct, sl_pct, quantity) -> dict:
        for attempt in range(self.MAX_RETRIES):
            try:
                result = self._execute(bond_code, base_price, tp_pct, sl_pct, quantity)
                if result['success']:
                    logger.info(f"[TpSl] OK: {bond_code} TP={tp_pct}% SL={sl_pct}%")
                    return result
                logger.warning(f"[TpSl] 第{attempt+1}次失败: {result['message']}")
            except Exception as e:
                logger.error(f"[TpSl] 第{attempt+1}次异常: {e}")
            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_INTERVAL)
        self._alert(bond_code, base_price, tp_pct, sl_pct)
        return {'success': False, 'message': f'重试{self.MAX_RETRIES}次失败'}

    def _execute(self, bond_code, base_price, tp_pct, sl_pct, quantity):
        import ctypes
        import ctypes.wintypes
        import subprocess
        from ctypes import windll, c_long, c_ulong, byref, Structure, WINFUNCTYPE

        class RECT(Structure):
            _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]

        def find_win(title_kw, class_name=None):
            found = []
            @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            def cb(hwnd, lp):
                if windll.user32.IsWindowVisible(hwnd):
                    length = windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                        if title_kw in buf.value:
                            if class_name:
                                cls = ctypes.create_unicode_buffer(256)
                                windll.user32.GetClassNameW(hwnd, cls, 256)
                                if class_name in cls.value:
                                    found.append(hwnd)
                            else:
                                found.append(hwnd)
                return True
            windll.user32.EnumWindows(cb, 0)
            return found[0] if found else None

        def activate_win(hwnd):
            """强制将窗口带到前台"""
            windll.user32.ShowWindow(hwnd, 9)
            windll.user32.keybd_event(0x12, 0, 0, 0)
            windll.user32.SetForegroundWindow(hwnd)
            windll.user32.keybd_event(0x12, 0, 2, 0)
            windll.user32.BringWindowToTop(hwnd)
            windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.3)

        def get_rect(hwnd):
            r = RECT()
            windll.user32.GetWindowRect(hwnd, byref(r))
            return r.left, r.top

        def click_rel(hwnd, key, wait=0.3):
            left, top = get_rect(hwnd)
            rx, ry = self.positions[key]
            windll.user32.SetCursorPos(int(left + rx), int(top + ry))
            time.sleep(0.1)
            windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.05)
            windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(wait)

        def scroll_rel(hwnd, key, clicks=1):
            left, top = get_rect(hwnd)
            rx, ry = self.positions[key]
            windll.user32.SetCursorPos(int(left + rx), int(top + ry))
            time.sleep(0.1)
            for _ in range(clicks):
                windll.user32.mouse_event(0x0800, 0, 0, c_ulong(4294967176).value, 0)
                time.sleep(0.3)

        def press_tab():
            windll.user32.keybd_event(0x09, 0, 0, 0)
            time.sleep(0.02)
            windll.user32.keybd_event(0x09, 0, 2, 0)
            time.sleep(0.1)

        def press_enter():
            windll.user32.keybd_event(0x0D, 0, 0, 0)
            time.sleep(0.05)
            windll.user32.keybd_event(0x0D, 0, 2, 0)
            time.sleep(0.2)

        def select_all():
            windll.user32.keybd_event(0x11, 0, 0, 0)
            windll.user32.keybd_event(0x41, 0, 0, 0)
            time.sleep(0.02)
            windll.user32.keybd_event(0x41, 0, 2, 0)
            windll.user32.keybd_event(0x11, 0, 2, 0)
            time.sleep(0.05)

        def type_text(text):
            process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-16le'))
            time.sleep(0.05)
            windll.user32.keybd_event(0x11, 0, 0, 0)
            windll.user32.keybd_event(0x56, 0, 0, 0)
            time.sleep(0.02)
            windll.user32.keybd_event(0x56, 0, 2, 0)
            windll.user32.keybd_event(0x11, 0, 2, 0)
            time.sleep(0.1)

        def type_number(value):
            select_all()
            text = f"{value:.3f}" if isinstance(value, float) else str(value)
            type_text(text)

        # --- 执行 ---
        hwnd_x = find_win(self.XIADAN_TITLE)
        if not hwnd_x:
            return {'success': False, 'message': 'xiadan.exe未找到'}
        
        # 检查弹窗是否已打开
        hwnd_p = find_win(self.POPUP_TITLE, self.POPUP_CLASS)
        
        if hwnd_p:
            # 弹窗已打开,直接复用(不关闭)
            activate_win(hwnd_p)
        else:
            # 弹窗未打开,点击条件单按钮打开
            for click_attempt in range(3):
                activate_win(hwnd_x)
                click_rel(hwnd_x, 'xiadan_condition_btn', wait=1.5)
                
                # 等待弹窗出现
                for _ in range(6):
                    hwnd_p = find_win(self.POPUP_TITLE, self.POPUP_CLASS)
                    if hwnd_p:
                        break
                    time.sleep(0.3)
                
                if hwnd_p:
                    break
                logger.warning(f"[TpSl] 点击条件单第{click_attempt+1}次未弹出窗口,重试...")
            
            if not hwnd_p:
                return {'success': False, 'message': '条件单弹窗未出现(重试3次失败)'}
            activate_win(hwnd_p)

        click_rel(hwnd_p, 'popup_sell_condition', wait=0.5)
        click_rel(hwnd_p, 'popup_tp_sl', wait=0.8)

        click_rel(hwnd_p, 'popup_code', wait=0.5)
        select_all()
        type_text(bond_code)
        time.sleep(0.5)

        press_tab(); time.sleep(0.1)
        type_number(base_price)
        press_tab(); time.sleep(0.1)
        type_number(tp_pct)
        press_tab(); time.sleep(0.1)
        type_number(sl_pct)
        press_tab(); time.sleep(0.1)
        type_number(quantity)

        # 滚动确保提交按钮可见 - 增加安全余量
        scroll_clicks = self.positions.get('scroll_clicks', 5)
        total_scrolls = scroll_clicks + 3  # 校准次数 + 3次安全余量
        logger.info(f"[TpSl] 滚动 {total_scrolls} 次 (校准{scroll_clicks}次 + 安全余量)")
        scroll_rel(hwnd_p, 'popup_scroll', clicks=total_scrolls)
        time.sleep(0.5)
        click_rel(hwnd_p, 'popup_submit_btn', wait=0.5)
        press_enter()
        time.sleep(0.5)

        return {'success': True, 'message': '条件单已提交'}

    def _load_positions(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        positions = {}
        for key, val in raw.get('xiadan', {}).items():
            positions[f'xiadan_{key}'] = val
        for key, val in raw.get('popup', {}).items():
            positions[f'popup_{key}'] = val
        scroll = raw.get('popup_scroll', {})
        if 'pos' in scroll:
            positions['popup_scroll'] = scroll['pos']
        positions['scroll_clicks'] = scroll.get('clicks', 5)  # 默认5次，确保能看到提交按钮
        return positions

    def _alert(self, bond_code, base_price, tp_pct, sl_pct):
        msg = f"[!!!] 条件单失败: {bond_code} 基准={base_price} TP={tp_pct}% SL={sl_pct}%"
        logger.critical(msg)
        try:
            import winsound
            for _ in range(3):
                winsound.MessageBeep(winsound.MB_ICONHAND)
                time.sleep(0.5)
        except:
            pass


# ==================== 串行订单管道 ====================

class OrderPipeline:
    MAX_QUEUE = 10
    CONFIRM_TIMEOUT = 30
    STATE_FILE = "pipeline_state.json"

    def __init__(self, config: dict):
        self._queue: List[dict] = []
        self._current: Optional[TradeOrder] = None
        self._history: List[dict] = []
        self._lock = threading.Lock()
        self._state_dir = Path(config.get('state_dir', '.'))
        self._trader_api_url = config.get('trader_api_url', 'http://127.0.0.1:8081')
        self._load_state()

    @property
    def current(self):
        return self._current

    @property
    def queue(self):
        return self._queue

    @property
    def history(self):
        return self._history[-20:]  # 最近20条

    def add(self, hit_info: dict) -> str:
        with self._lock:
            if self._current is None:
                self._create_order(hit_info)
                return "processing"
            if len(self._queue) >= self.MAX_QUEUE:
                self._queue.pop(0)
            if 'hit_time' not in hit_info:
                hit_info['hit_time'] = datetime.now().isoformat()
            self._queue.append(hit_info)
            return "queued"

    def on_bought(self):
        """兼容接口(一步确认模式下不需要单独调用)"""
        pass

    def on_confirm(self) -> Optional[TradeOrder]:
        """一步确认: 直接从wait_buy→filled, 触发止盈止损"""
        with self._lock:
            if self._current and self._current.status in ("wait_buy", "confirming"):
                self._current.status = "filled"
                self._current.confirmed_at = datetime.now().isoformat()
                self._save_state()
                logger.info(f"[Pipeline] 一步确认: {self._current.bond_name}")
                return self._current
        return None

    def on_cancel(self):
        """手动撤单"""
        with self._lock:
            if self._current and self._current.status in ("confirming", "wait_buy"):
                self._do_cancel("manual")

    def on_skip(self):
        """跳过"""
        with self._lock:
            if self._current:
                self._current.status = "skipped"
                self._add_history()
                self._current = None
                self._process_next()
                self._save_state()

    def mark_tp_sl_done(self, order_id: str):
        with self._lock:
            if self._current and self._current.order_id == order_id:
                self._current.status = "tp_sl_set"
                self._current.tp_sl_set_at = datetime.now().isoformat()
                self._add_history()
                self._current = None
                self._process_next()
                self._save_state()

    def mark_failed(self, order_id: str, error: str):
        with self._lock:
            if self._current and self._current.order_id == order_id:
                self._current.status = "failed"
                self._current.error_msg = error
                self._add_history()
                self._current = None
                self._process_next()
                self._save_state()

    def check_timeout(self):
        """每秒调用:检查超时(当前订单+队列)"""
        with self._lock:
            # 1. 当前订单超时
            if self._current and self._current.status in ("wait_buy", "confirming") and self._current.bought_at:
                bought_time = datetime.fromisoformat(self._current.bought_at)
                elapsed = (datetime.now() - bought_time).total_seconds()
                if elapsed >= self.CONFIRM_TIMEOUT:
                    logger.info(f"[Pipeline] 30秒超时,自动撤单: {self._current.bond_name}")
                    self._do_cancel("timeout")
            
            # 2. 队列中超时的订单自动移除(从命中时间算30秒)
            if self._queue:
                now = datetime.now()
                expired = []
                remaining = []
                for item in self._queue:
                    hit_time = item.get('hit_time')
                    if hit_time:
                        elapsed = (now - datetime.fromisoformat(hit_time)).total_seconds()
                        if elapsed >= self.CONFIRM_TIMEOUT:
                            expired.append(item)
                            continue
                    remaining.append(item)
                
                if expired:
                    self._queue = remaining
                    for item in expired:
                        logger.info(f"[Pipeline] 队列超时移除: {item.get('bond_code')} {item.get('bond_name')}")
                        # 记录到历史
                        self._history.append({
                            'order_id': f"{item.get('bond_code')}_queue_timeout",
                            'bond_code': item.get('bond_code', ''),
                            'bond_name': item.get('bond_name', ''),
                            'status': 'timeout_cancelled',
                            'created_at': item.get('queued_at', ''),
                            'target_buy_price': 0,
                            'tp_pct': item.get('tp_pct', 0),
                            'sl_pct': item.get('sl_pct', 0),
                            'quantity': item.get('lots', 1) * 10,
                            'error_msg': '队列超时自动移除',
                        })
                    self._save_state()

    def get_countdown(self) -> int:
        """获取当前倒计时秒数"""
        if self._current and self._current.status in ("wait_buy", "confirming") and self._current.bought_at:
            bought_time = datetime.fromisoformat(self._current.bought_at)
            elapsed = (datetime.now() - bought_time).total_seconds()
            return max(0, int(self.CONFIRM_TIMEOUT - elapsed))
        return -1

    def _do_cancel(self, reason: str):
        """执行撤单"""
        order = self._current
        # 调用撤单API
        try:
            url = f"{self._trader_api_url}/api/cancel_order"
            resp = requests.post(url, json={
                'code': order.bond_code, 'direction': 'buy'
            }, timeout=5)
            logger.info(f"[Pipeline] 撤单API: {resp.status_code}")
        except Exception as e:
            logger.warning(f"[Pipeline] 撤单API失败(不阻断): {e}")

        order.status = "timeout_cancelled" if reason == "timeout" else "cancelled"
        self._add_history()
        self._current = None
        self._process_next()
        self._save_state()

    def _create_order(self, hit_info: dict):
        hit_price = hit_info['hit_price']
        offset = hit_info.get('price_offset', 0)
        mode = hit_info.get('offset_mode', 'fixed')

        if mode == 'percent':
            buy_price = round(hit_price * (1 + offset / 100), 3)
        else:
            buy_price = round(hit_price + offset, 3)

        now_str = datetime.now().isoformat()
        order = TradeOrder(
            order_id=f"{hit_info['bond_code']}_{int(time.time()*1000)}",
            bond_code=hit_info['bond_code'],
            bond_name=hit_info.get('bond_name', ''),
            scheme_name=hit_info.get('scheme_name', ''),
            hit_price=hit_price,
            price_offset=offset,
            offset_mode=mode,
            target_buy_price=buy_price,
            tp_pct=hit_info.get('tp_pct', 3.0),
            sl_pct=hit_info.get('sl_pct', 2.0),
            lots=hit_info.get('lots', 1),
            quantity=hit_info.get('lots', 1) * 10,
            status="wait_buy",
            created_at=now_str,
            bought_at=now_str,  # 30秒倒计时从创建开始
        )
        self._current = order
        self._save_state()
        logger.info(f"[Pipeline] 新单: {order.bond_name}({order.bond_code}) @{buy_price}")

    def _process_next(self):
        if self._queue:
            self._create_order(self._queue.pop(0))

    def _add_history(self):
        if self._current:
            self._history.append(asdict(self._current))
            if len(self._history) > 50:
                self._history = self._history[-50:]

    def _save_state(self):
        try:
            state = {
                'current': asdict(self._current) if self._current else None,
                'queue': self._queue,
                'history': self._history,
            }
            (self._state_dir / self.STATE_FILE).write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as e:
            logger.warning(f"[Pipeline] 保存失败: {e}")

    def _load_state(self):
        try:
            path = self._state_dir / self.STATE_FILE
            if path.exists():
                state = json.loads(path.read_text(encoding='utf-8'))
                if state.get('current'):
                    self._current = TradeOrder(**state['current'])
                self._queue = state.get('queue', [])
                self._history = state.get('history', [])
        except Exception as e:
            logger.warning(f"[Pipeline] 加载失败: {e}")


# ==================== 主入口 ====================

class TradeFlowManager:
    """monitor_bond.py 直接调用的接口"""

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get('enabled', True)
        self.pipeline = OrderPipeline(config)

        positions_file = config.get('positions_file', '')
        if positions_file and Path(positions_file).exists():
            self.tp_sl_placer = TpSlPlacer(positions_file)
        else:
            self.tp_sl_placer = None
            logger.warning("[TradeFlow] 无校准文件,止盈止损功能不可用")

        self.trader_api_url = config.get('trader_api_url', 'http://127.0.0.1:8081')

    def on_hit(self, bond_code, bond_name, hit_price, scheme_detail, lots=1):
        """量化命中时调用"""
        if not self.enabled:
            return
        hit_info = {
            'bond_code': bond_code,
            'bond_name': bond_name,
            'hit_price': hit_price,
            'price_offset': scheme_detail.get('price_offset', 0),
            'offset_mode': scheme_detail.get('offset_mode', 'fixed'),
            'tp_pct': scheme_detail.get('take_profit', 3.0),
            'sl_pct': scheme_detail.get('stop_loss', 2.0),
            'scheme_name': scheme_detail.get('name', ''),
            'lots': lots,
            'hit_time': datetime.now().isoformat(),  # 命中时间(超时从此刻算)
        }
        result = self.pipeline.add(hit_info)
        if result == "processing":
            self._fill_buy_order(self.pipeline.current)

    def on_bought(self):
        """面板: 用户点了买入"""
        self.pipeline.on_bought()

    def on_confirm(self):
        """面板: 确认成交→设置止盈止损"""
        order = self.pipeline.on_confirm()
        if not order:
            return
        if self.tp_sl_placer:
            threading.Thread(target=self._submit_tp_sl, args=(order,), daemon=True).start()
        else:
            self.pipeline.mark_failed(order.order_id, "无校准文件")

    def on_cancel(self):
        """面板: 撤单"""
        self.pipeline.on_cancel()

    def on_skip(self):
        """面板: 跳过"""
        self.pipeline.on_skip()

    def check_timeout(self):
        """每秒/每tick调用"""
        self.pipeline.check_timeout()

    def get_status(self) -> dict:
        """API返回状态"""
        current = self.pipeline.current
        return {
            'current': asdict(current) if current else None,
            'countdown': self.pipeline.get_countdown(),
            'queue': self.pipeline.queue,
            'history': self.pipeline.history,
        }

    def _fill_buy_order(self, order: TradeOrder):
        try:
            resp = requests.post(f"{self.trader_api_url}/api/prepare_buy", json={
                'code': order.bond_code,
                'name': order.bond_name,
                'price': order.target_buy_price,
                'lots': order.lots,
            }, timeout=5)
            logger.info(f"[TradeFlow] 买入填充: {resp.json()}")
        except Exception as e:
            logger.warning(f"[TradeFlow] 买入填充失败: {e}")

    def _submit_tp_sl(self, order: TradeOrder):
        result = self.tp_sl_placer.place(
            bond_code=order.bond_code,
            base_price=order.target_buy_price,
            tp_pct=order.tp_pct,
            sl_pct=order.sl_pct,
            quantity=order.quantity,
        )
        if result['success']:
            self.pipeline.mark_tp_sl_done(order.order_id)
        else:
            self.pipeline.mark_failed(order.order_id, result['message'])


# 全局单例
_instance: Optional[TradeFlowManager] = None

def get_trade_flow_manager(config: dict = None) -> TradeFlowManager:
    global _instance
    if _instance is None:
        if config is None:
            config = {
                'enabled': True,
                'positions_file': str(Path(__file__).parent / 'tp_sl_positions.json'),
                'state_dir': str(Path(__file__).parent),
                'trader_api_url': 'http://127.0.0.1:8081',
            }
        _instance = TradeFlowManager(config)
    return _instance







