"""
止盈止损条件单自动化下单器（独立模块）

从 trade_flow.py 抽取，供 auto_trader.py 和 trade_flow.py 共用。
纯 Win32 API 实现，依赖 tp_sl_positions.json 坐标校准文件。

用法:
    from tp_sl_placer import TpSlPlacer
    placer = TpSlPlacer(positions_file="tp_sl_positions.json")
    result = placer.place(bond_code, base_price, tp_pct, sl_pct, quantity)
"""

import time
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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
