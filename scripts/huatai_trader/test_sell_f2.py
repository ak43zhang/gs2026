"""
强平卖出(F2) - 探测与测试脚本
探测xiadan.exe的卖出面板, 记录操作流程

场景: 持仓超时需要强制卖出时, 自动填充卖出表单
流程: F2切到卖出面板 → 输入代码/价格/数量 → (你点卖出)
"""

import time
import sys
import json
import ctypes
import ctypes.wintypes
from ctypes import windll, Structure, c_long, c_ulong, byref, WINFUNCTYPE
from pathlib import Path
import subprocess

# ==================== 配置 ====================

XIADAN_TITLE = "网上股票交易系统5.0"

# 测试数据(改为你持仓的转债)
TEST_CODE = "123188"
TEST_PRICE = 131      # 卖出价格
TEST_QUANTITY = 10        # 股数

ACTUALLY_SUBMIT = False   # True=真的点卖出, False=只填表不提交

# ==================== 底层工具 ====================

class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]

class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]

def get_mouse_pos():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt.x, pt.y

def find_window(title_kw):
    found = []
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if windll.user32.IsWindowVisible(hwnd):
            length = windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                if title_kw in buf.value:
                    found.append(hwnd)
        return True
    windll.user32.EnumWindows(cb, 0)
    return found[0] if found else None

def activate(hwnd):
    windll.user32.ShowWindow(hwnd, 9)
    windll.user32.keybd_event(0x12, 0, 0, 0)
    windll.user32.SetForegroundWindow(hwnd)
    windll.user32.keybd_event(0x12, 0, 2, 0)
    windll.user32.BringWindowToTop(hwnd)
    windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)

def get_window_rect(hwnd):
    r = RECT()
    windll.user32.GetWindowRect(hwnd, byref(r))
    return r.left, r.top

def press_key(vk):
    windll.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.keybd_event(vk, 0, 2, 0)
    time.sleep(0.3)

def press_tab():
    windll.user32.keybd_event(0x09, 0, 0, 0)
    time.sleep(0.02)
    windll.user32.keybd_event(0x09, 0, 2, 0)
    time.sleep(0.1)

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

def click_abs(x, y, wait=0.3):
    windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.02)
    windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(wait)


# ==================== 主流程 ====================

def main():
    print("""
+======================================================+
|  强平卖出(F2) - 探测与测试                            |
|                                                      |
|  目的: 了解xiadan卖出面板, 测试自动填表                 |
|  两种模式: 探测(记录坐标) / 填充测试                   |
+======================================================+
    """)
    
    print("  选择:")
    print("  1. 探测模式(首次,记录F2面板坐标和Tab顺序)")
    print("  2. 填充测试(已知Tab顺序,测试自动填表)")
    mode = input("  选择(1/2): ").strip()
    
    if mode == '1':
        probe_mode()
    elif mode == '2':
        fill_mode()
    else:
        print("  无效选择")


def probe_mode():
    """探测模式: 记录F2卖出面板的布局和Tab顺序"""
    
    result = {
        'tab_order': [],
        'positions': {},
        'notes': [],
    }
    
    # === 找到xiadan ===
    print("\n" + "─" * 50)
    print("  步骤1: 找到xiadan并切到F2")
    print("─" * 50)
    
    hwnd = find_window(XIADAN_TITLE)
    if not hwnd:
        print(f"  [FAIL] 未找到'{XIADAN_TITLE}'")
        return
    
    activate(hwnd)
    print(f"  [OK] xiadan已激活")
    
    print("\n  即将按F2切到卖出面板...")
    input("  按Enter > ")
    
    press_key(0x71)  # F2
    time.sleep(0.5)
    print("  [OK] 已按F2")
    
    # === 记录坐标 ===
    print("\n" + "─" * 50)
    print("  步骤2: 记录卖出面板字段位置")
    print("─" * 50)
    print()
    
    win_left, win_top = get_window_rect(hwnd)
    
    fields = [
        ('code', '证券代码输入框'),
        ('price', '卖出价格输入框'),
        ('quantity', '卖出数量输入框'),
        ('sell_btn', '卖出按钮'),
    ]
    
    for key, label in fields:
        print(f"  ➜ 鼠标移到【{label}】上")
        input(f"    按Enter > ")
        mx, my = get_mouse_pos()
        result['positions'][key] = [mx - win_left, my - win_top]
        print(f"    ✓ ({mx - win_left}, {my - win_top})")
    
    # === Tab顺序探测 ===
    print("\n" + "─" * 50)
    print("  步骤3: Tab顺序探测")
    print("─" * 50)
    print()
    print("  请点击证券代码输入框, 让光标在里面")
    input("  按Enter, 脚本会自动点回代码框再按Tab > ")
    
    # 点击代码框恢复焦点
    code_pos = result['positions']['code']
    click_abs(win_left + code_pos[0], win_top + code_pos[1], wait=0.5)
    
    print("  焦点应在代码框了, 开始Tab探测:")
    print("  输入: price/quantity/sell_btn/other/q退出")
    print()
    
    tab_order = ['code']
    for i in range(8):
        press_tab()
        time.sleep(0.3)
        field = input(f"  Tab[{i+1}] -> ").strip()
        if not field or field == 'q':
            break
        tab_order.append(field)
    
    result['tab_order'] = tab_order
    print(f"\n  ✓ Tab顺序: {' -> '.join(tab_order)}")
    
    # === 补充问题 ===
    print("\n" + "─" * 50)
    print("  步骤4: 补充信息")
    print("─" * 50)
    
    q1 = input("  F2面板和F1买入面板的布局一样吗? (y=一样/n=不同): ").strip().lower()
    result['notes'].append(f"F2与F1布局相同: {'是' if q1=='y' else '否'}")
    
    q2 = input("  输入代码后需要等待加载吗? (y/n): ").strip().lower()
    result['notes'].append(f"代码需等待: {'是' if q2=='y' else '否'}")
    
    q3 = input("  点卖出按钮后有确认弹窗吗? (y/n/不确定): ").strip()
    result['notes'].append(f"卖出确认弹窗: {q3}")
    
    # === 保存 ===
    output_file = Path(__file__).parent / "sell_config.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"""
{'='*50}
  F2卖出面板探测完成! 保存到: {output_file}
{'='*50}

  Tab顺序: {' -> '.join(result['tab_order'])}
  坐标: {result['positions']}
  备注: {'; '.join(result['notes'])}
  
  请把结果发给我!
""")


def fill_mode():
    """填充测试: 用已知的Tab顺序自动填表"""
    
    print(f"""
  测试数据:
    代码: {TEST_CODE}
    价格: {TEST_PRICE}
    数量: {TEST_QUANTITY}
    提交: {'是(!!!)' if ACTUALLY_SUBMIT else '否(只填表)'}
    """)
    
    # 加载配置
    config_file = Path(__file__).parent / "sell_config.json"
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"  Tab顺序: {' -> '.join(config.get('tab_order', []))}")
    else:
        print("  [!] 未找到sell_config.json, 使用默认Tab顺序: code→price→quantity")
        config = {'tab_order': ['code', 'price', 'quantity', 'sell_btn'], 'positions': {}}
    
    input("\n  按Enter开始填充 > ")
    
    # 找到xiadan
    hwnd = find_window(XIADAN_TITLE)
    if not hwnd:
        print("  [FAIL] 未找到xiadan")
        return
    
    activate(hwnd)
    time.sleep(0.2)
    
    # 按F2
    press_key(0x71)  # F2
    time.sleep(0.5)
    print("  [OK] F2卖出面板")
    
    # 点击代码框(如果有坐标)
    if config['positions'].get('code'):
        win_left, win_top = get_window_rect(hwnd)
        cx, cy = config['positions']['code']
        click_abs(win_left + cx, win_top + cy, wait=0.3)
    
    # 填充代码
    select_all()
    type_text(TEST_CODE)
    time.sleep(0.8)  # 等待代码加载
    print(f"  代码: {TEST_CODE}")
    
    # Tab到价格
    press_tab()
    time.sleep(0.1)
    type_number(TEST_PRICE)
    print(f"  价格: {TEST_PRICE}")
    
    # Tab到数量
    press_tab()
    time.sleep(0.1)
    type_number(TEST_QUANTITY)
    print(f"  数量: {TEST_QUANTITY}")
    
    print("\n  [OK] 填充完成!")
    
    if ACTUALLY_SUBMIT:
        confirm = input("  !!! 输入YES确认卖出: ").strip()
        if confirm == 'YES':
            press_tab()
            time.sleep(0.1)
            press_key(0x0D)  # Enter
            time.sleep(0.5)
            press_key(0x0D)  # 确认弹窗
            print("  [OK] 已提交卖出!")
        else:
            print("  取消")
    else:
        print("  (ACTUALLY_SUBMIT=False, 未提交)")
    
    # 切回F1
    print("\n  切回F1...")
    press_key(0x70)  # F1
    print("  [OK]")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
