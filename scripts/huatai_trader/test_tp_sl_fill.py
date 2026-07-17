"""
止盈止损条件单 - 自动填充测试 v3
改进: 使用窗口相对坐标,窗口移动不影响

首次运行: 记录窗口位置,将绝对坐标转为相对坐标
后续运行: 获取当前窗口位置,动态计算绝对坐标
"""

import time
import sys
import json
import ctypes
import ctypes.wintypes
import traceback
from ctypes import windll, Structure, c_long, c_ulong, byref, WINFUNCTYPE
from pathlib import Path

# ==================== 命中参数 ====================

BOND_CODE = "127045"         # 转债代码
BUY_PRICE = 105.300          # 买入成交价 -> 基准价
TP_PCT = 3.0                 # 止盈百分比
SL_PCT = 2.0                 # 止损百分比
QUANTITY = 10                # 数量
ACTUALLY_SUBMIT = False      # 是否提交

# ==================== 窗口配置 ====================

XIADAN_TITLE = "网上股票交易系统5.0"
POPUP_TITLE = "华泰理财通"
POPUP_CLASS = "Chrome_WidgetWin_1"

# ==================== 坐标配置文件 ====================
# 首次运行会生成此文件(相对坐标),后续自动加载
CONFIG_FILE = Path(__file__).parent / "tp_sl_positions.json"

# ==================== 底层操作 ====================

class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]

class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]

def get_mouse_pos():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt.x, pt.y

def get_window_rect(hwnd):
    """获取窗口屏幕位置"""
    rect = RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom

def find_window(title_keyword, class_name=None):
    found = []
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def callback(hwnd, lparam):
        if windll.user32.IsWindowVisible(hwnd):
            length = windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                if title_keyword in buf.value:
                    if class_name:
                        cls_buf = ctypes.create_unicode_buffer(256)
                        windll.user32.GetClassNameW(hwnd, cls_buf, 256)
                        if class_name in cls_buf.value:
                            found.append(hwnd)
                    else:
                        found.append(hwnd)
        return True
    windll.user32.EnumWindows(callback, 0)
    return found[0] if found else None

def activate(hwnd):
    windll.user32.ShowWindow(hwnd, 9)
    time.sleep(0.1)
    windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)

def click(x, y, wait=0.3):
    windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.1)
    windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(wait)

def type_text(text):
    import subprocess
    process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
    process.communicate(text.encode('utf-16le'))
    time.sleep(0.1)
    windll.user32.keybd_event(0x11, 0, 0, 0)
    windll.user32.keybd_event(0x56, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.keybd_event(0x56, 0, 2, 0)
    windll.user32.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.2)

def select_all():
    windll.user32.keybd_event(0x11, 0, 0, 0)
    windll.user32.keybd_event(0x41, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.keybd_event(0x41, 0, 2, 0)
    windll.user32.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.1)

def press_tab():
    windll.user32.keybd_event(0x09, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.keybd_event(0x09, 0, 2, 0)
    time.sleep(0.2)

def press_enter():
    windll.user32.keybd_event(0x0D, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.keybd_event(0x0D, 0, 2, 0)
    time.sleep(0.2)

def scroll_down(x, y, clicks=1):
    windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.1)
    for _ in range(clicks):
        windll.user32.mouse_event(0x0800, 0, 0, c_ulong(4294967176).value, 0)  # -120
        time.sleep(0.3)

def type_number(value):
    select_all()
    time.sleep(0.1)
    text = f"{value:.3f}" if isinstance(value, float) else str(value)
    type_text(text)


# ==================== 坐标管理 ====================

class PositionManager:
    """
    管理相对坐标
    存储: 每个元素相对于所属窗口左上角的偏移
    使用: 运行时获取窗口当前位置 + 偏移 = 实际屏幕坐标
    """
    
    def __init__(self):
        self.xiadan = {}   # xiadan窗口的元素相对坐标
        self.popup = {}    # 弹窗的元素相对坐标
        self.popup_scroll = {}
    
    def save(self, path):
        data = {
            'xiadan': self.xiadan,
            'popup': self.popup,
            'popup_scroll': self.popup_scroll,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.xiadan = data.get('xiadan', {})
        self.popup = data.get('popup', {})
        self.popup_scroll = data.get('popup_scroll', {})
    
    def abs_click(self, hwnd, key, wait=0.3):
        """根据窗口当前位置+相对偏移,点击"""
        left, top, _, _ = get_window_rect(hwnd)
        
        # 决定用哪个坐标集
        if key in self.xiadan:
            rx, ry = self.xiadan[key]
        elif key in self.popup:
            rx, ry = self.popup[key]
        else:
            raise KeyError(f"未知坐标key: {key}")
        
        abs_x = left + rx
        abs_y = top + ry
        click(abs_x, abs_y, wait)
    
    def abs_scroll(self, hwnd, clicks=1):
        """在滚动位置执行滚动"""
        left, top, _, _ = get_window_rect(hwnd)
        rx, ry = self.popup_scroll['pos']
        scroll_down(left + rx, top + ry, clicks)


# ==================== 首次校准 ====================

def calibrate():
    """引导用户记录所有坐标(转为相对坐标保存)"""
    print("""
╔══════════════════════════════════════════╗
║  首次校准: 记录各元素位置(只需做一次)     ║
║  鼠标移到目标 -> 回这里按Enter            ║
╚══════════════════════════════════════════╝
    """)
    
    pm = PositionManager()
    
    # --- xiadan部分 ---
    print("─── xiadan.exe ───")
    print("  请确保xiadan.exe主窗口可见")
    input("  鼠标放在xiadan窗口上,按Enter > ")
    
    hwnd_x = find_window(XIADAN_TITLE)
    if not hwnd_x:
        print(f"  [FAIL] 找不到'{XIADAN_TITLE}'")
        return
    x_left, x_top, _, _ = get_window_rect(hwnd_x)
    print(f"  ✓ xiadan窗口位置: ({x_left}, {x_top})")
    
    print("\n  鼠标移到xiadan中的[条件单]按钮上")
    input("  按Enter > ")
    mx, my = get_mouse_pos()
    pm.xiadan['condition_btn'] = [mx - x_left, my - x_top]
    print(f"  ✓ 相对坐标: ({mx - x_left}, {my - x_top})")
    
    # 点击条件单打开弹窗
    print("\n  请点击[条件单]打开弹窗")
    input("  弹窗出现后按Enter > ")
    
    # --- 弹窗部分 ---
    print("\n─── 华泰理财通弹窗 ───")
    hwnd_p = find_window(POPUP_TITLE, POPUP_CLASS)
    if not hwnd_p:
        print(f"  [FAIL] 找不到'{POPUP_TITLE}'弹窗")
        return
    p_left, p_top, _, _ = get_window_rect(hwnd_p)
    print(f"  ✓ 弹窗位置: ({p_left}, {p_top})")
    
    fields = [
        ('sell_condition', '卖出条件单'),
        ('tp_sl', '止盈止损'),
    ]
    
    for key, label in fields:
        print(f"\n  鼠标移到【{label}】上")
        input("  按Enter > ")
        mx, my = get_mouse_pos()
        pm.popup[key] = [mx - p_left, my - p_top]
        print(f"  ✓ ({mx - p_left}, {my - p_top})")
        print(f"  请点击它")
        input("  按Enter > ")
        time.sleep(0.5)
    
    # 表单字段
    form_fields = [
        ('code', '证券代码输入框'),
        ('base_price', '基准价输入框'),
        ('tp_price', '止盈条件输入框'),
        ('sl_price', '止损条件输入框'),
        ('price_type', '委托价下拉框'),
        ('quantity', '委托数量输入框'),
    ]
    
    # 刷新弹窗位置(可能在操作中移动了)
    p_left, p_top, _, _ = get_window_rect(hwnd_p)
    
    print("\n─── 表单字段 ───")
    for key, label in form_fields:
        print(f"  鼠标移到【{label}】上")
        input("  按Enter > ")
        mx, my = get_mouse_pos()
        pm.popup[key] = [mx - p_left, my - p_top]
        print(f"  ✓ ({mx - p_left}, {my - p_top})")
    
    # 滚动区域
    print("\n  鼠标放在表单可滚动区域内")
    input("  按Enter > ")
    mx, my = get_mouse_pos()
    pm.popup_scroll['pos'] = [mx - p_left, my - p_top]
    
    # 滚动到提交按钮
    print("  请滚动到能看到[提交条件单]按钮")
    input("  按Enter > ")
    
    n = input("  滚了几下鼠标滚轮? (如1): ").strip()
    pm.popup_scroll['clicks'] = int(n) if n.isdigit() else 1
    
    print("\n  鼠标移到【提交条件单】按钮上")
    input("  按Enter > ")
    mx, my = get_mouse_pos()
    # 注意: 提交按钮是滚动后才可见的,但相对窗口的偏移不变(是内容滚动,窗口没动)
    pm.popup['submit_btn'] = [mx - p_left, my - p_top]
    print(f"  ✓ ({mx - p_left}, {my - p_top})")
    
    # 保存
    pm.save(CONFIG_FILE)
    print(f"\n{'='*50}")
    print(f"  校准完成! 已保存到: {CONFIG_FILE}")
    print(f"  以后窗口随便移动都没问题")
    print(f"  重新运行脚本即可测试填充")
    print(f"{'='*50}")


# ==================== 执行填充 ====================

def run():
    """正式执行止盈止损填充"""
    
    pm = PositionManager()
    pm.load(CONFIG_FILE)
    
    print(f"""
╔══════════════════════════════════════════╗
║  止盈止损自动设置                         ║
╠══════════════════════════════════════════╣
║  代码:   {BOND_CODE:10s}                 ║
║  基准价: {BUY_PRICE:<10.3f}              ║
║  止盈:   {TP_PCT}%                       ║
║  止损:   {SL_PCT}%                       ║
║  数量:   {QUANTITY}                      ║
║  提交:   {'是' if ACTUALLY_SUBMIT else '否'}                         ║
╚══════════════════════════════════════════╝
    """)
    input("  按Enter开始 > ")
    
    # 1. 找到xiadan
    print("  [1/7] 找xiadan...")
    hwnd_x = find_window(XIADAN_TITLE)
    if not hwnd_x:
        print(f"  [FAIL] 未找到'{XIADAN_TITLE}'")
        return
    activate(hwnd_x)
    print("  [OK]")
    
    # 2. 点击条件单
    print("  [2/7] 点击[条件单]...")
    pm.abs_click(hwnd_x, 'condition_btn', wait=2.5)
    print("  [OK] 等待弹窗...")
    
    # 3. 找到弹窗
    hwnd_p = None
    for _ in range(10):
        hwnd_p = find_window(POPUP_TITLE, POPUP_CLASS)
        if hwnd_p:
            break
        time.sleep(0.5)
    if not hwnd_p:
        print("  [FAIL] 弹窗未出现")
        return
    activate(hwnd_p)
    print("  [3/7] 弹窗已激活")
    
    # 4. 导航
    print("  [4/7] 导航: 卖出条件单 -> 止盈止损...")
    pm.abs_click(hwnd_p, 'sell_condition', wait=1.0)
    pm.abs_click(hwnd_p, 'tp_sl', wait=1.5)
    print("  [OK]")
    
    # 5. 填充
    print("  [5/7] 填充表单...")
    
    pm.abs_click(hwnd_p, 'code', wait=0.5)
    select_all()
    type_text(BOND_CODE)
    time.sleep(1.0)
    print(f"    代码: {BOND_CODE}")
    
    press_tab(); time.sleep(0.3)
    type_number(BUY_PRICE)
    print(f"    基准价: {BUY_PRICE}")
    
    press_tab(); time.sleep(0.3)
    type_number(TP_PCT)
    print(f"    止盈: {TP_PCT}%")
    
    press_tab(); time.sleep(0.3)
    type_number(SL_PCT)
    print(f"    止损: {SL_PCT}%")
    
    press_tab(); time.sleep(0.3)
    type_number(QUANTITY)
    print(f"    数量: {QUANTITY}")
    print("  [OK]")
    
    # 6. 滚动 - 确保能看到提交按钮
    print("  [6/7] 滚动...")
    
    # 获取校准时的滚动次数，如果没有则默认5次
    scroll_clicks = pm.popup_scroll.get('clicks', 5)
    
    # 先滚动到顶部(确保从顶部开始)
    # 向上滚动几次抵消可能的之前滚动
    pm.abs_scroll(hwnd_p, -10)  # 负数表示向上滚动
    time.sleep(0.3)
    
    # 然后向下滚动足够次数，确保提交按钮可见
    # 增加额外滚动次数作为安全余量
    total_scrolls = scroll_clicks + 3  # 校准次数 + 3次安全余量
    print(f"    滚动 {total_scrolls} 次 (校准{scroll_clicks}次 + 安全余量)...")
    pm.abs_scroll(hwnd_p, total_scrolls)
    time.sleep(0.5)
    print("  [OK]")
    
    # 7. 提交
    if ACTUALLY_SUBMIT:
        print("  [7/7] 提交...")
        confirm = input("  输入YES确认: ").strip()
        if confirm == 'YES':
            pm.abs_click(hwnd_p, 'submit_btn', wait=1.5)
            press_enter()
            print("  [OK] 已提交!")
        else:
            print("  [--] 取消")
    else:
        print("  [7/7] 不提交")
    
    print(f"\n  完成! 请检查弹窗中的填充内容")


# ==================== 入口 ====================

if __name__ == '__main__':
    if not CONFIG_FILE.exists():
        calibrate()
    else:
        print(f"  已有配置: {CONFIG_FILE}")
        print("  1. 执行填充")
        print("  2. 重新校准")
        c = input("  选择(1/2): ").strip()
        if c == '2':
            calibrate()
        else:
            try:
                run()
            except KeyboardInterrupt:
                print("\n中断")
            except Exception as e:
                print(f"\n错误: {e}")
                traceback.print_exc()


