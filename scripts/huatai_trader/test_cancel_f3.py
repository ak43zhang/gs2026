"""
撤单(F3) - 探测与测试脚本
探测xiadan.exe的撤单面板, 记录操作流程

流程: F3切到撤单面板 → 找到目标委托 → 撤单
"""

import time
import sys
import json
import ctypes
import ctypes.wintypes
from ctypes import windll, Structure, c_long, c_ulong, byref, WINFUNCTYPE
from pathlib import Path

# ==================== 配置 ====================

XIADAN_TITLE = "网上股票交易系统5.0"

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

def click_abs(x, y, wait=0.3):
    windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.02)
    windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(wait)

def double_click_abs(x, y, wait=0.3):
    windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.02)
    windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.02)
    windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(wait)


# ==================== 主流程 ====================

def main():
    print("""
+======================================================+
|  撤单(F3) - 探测与测试                                |
|                                                      |
|  目的: 了解xiadan撤单面板的操作方式                     |
|  方法: 鼠标移到目标 → 回这里按Enter                    |
+======================================================+
    """)

    result = {
        'xiadan_hwnd': None,
        'panel_info': {},
        'cancel_method': '',
        'positions': {},
        'notes': [],
    }

    # === 步骤1: 找到xiadan ===
    print("─" * 50)
    print("  步骤1: 找到xiadan.exe")
    print("─" * 50)
    
    hwnd = find_window(XIADAN_TITLE)
    if not hwnd:
        print(f"  [FAIL] 未找到'{XIADAN_TITLE}'")
        print("  请确保华泰xiadan.exe已打开")
        return
    
    activate(hwnd)
    print(f"  [OK] xiadan已激活 (handle={hwnd})")
    result['xiadan_hwnd'] = hwnd

    # === 步骤2: 按F3切到撤单面板 ===
    print("\n" + "─" * 50)
    print("  步骤2: 按F3切到撤单面板")
    print("─" * 50)
    print()
    print("  前提: xiadan中需要有至少1笔未成交委托(挂单)")
    print("  如果没有,请先挂一个不会成交的单(如极低价买入)")
    print()
    
    ready = input("  有未成交委托了吗? (y=有/n=没有,先去挂一个): ").strip().lower()
    if ready != 'y':
        print("  请先去挂一个不会成交的委托,然后重新运行")
        return
    
    print("\n  即将按F3切到撤单面板...")
    input("  按Enter继续 > ")
    
    activate(hwnd)
    time.sleep(0.2)
    press_key(0x72)  # F3
    time.sleep(1.0)
    print("  [OK] 已按F3")

    # === 步骤3: 观察撤单面板 ===
    print("\n" + "─" * 50)
    print("  步骤3: 观察撤单面板布局")
    print("─" * 50)
    print()
    print("  请观察xiadan当前显示的撤单面板,回答以下问题:")
    print()
    
    q1 = input("  1. 面板中能看到未成交委托列表吗? (y/n): ").strip().lower()
    result['notes'].append(f"有委托列表: {'是' if q1=='y' else '否'}")
    
    q2 = input("  2. 列表中每行包含什么信息? (如: 代码/名称/价格/数量/状态): ").strip()
    result['notes'].append(f"列表列信息: {q2}")
    
    q3 = input("  3. 撤单方式是? (如: 双击该行/选中后点撤单按钮/右键撤单): ").strip()
    result['cancel_method'] = q3
    result['notes'].append(f"撤单方式: {q3}")
    
    q4 = input("  4. 有没有[全撤]按钮? (y/n): ").strip().lower()
    result['notes'].append(f"有全撤按钮: {'是' if q4=='y' else '否'}")
    
    q5 = input("  5. 有没有[撤单]按钮(针对选中行)? (y/n): ").strip().lower()
    result['notes'].append(f"有撤单按钮: {'是' if q5=='y' else '否'}")

    # === 步骤4: 记录坐标 ===
    print("\n" + "─" * 50)
    print("  步骤4: 记录关键位置坐标")
    print("─" * 50)
    print()
    
    win_left, win_top = get_window_rect(hwnd)
    print(f"  xiadan窗口位置: ({win_left}, {win_top})")
    print()
    
    # 委托列表第一行
    print("  ➜ 鼠标移到委托列表的【第一行】上(任意位置)")
    input("    按Enter > ")
    mx, my = get_mouse_pos()
    result['positions']['first_row'] = [mx - win_left, my - win_top]
    print(f"    ✓ 第一行: 相对({mx - win_left}, {my - win_top})")
    
    # 如果有撤单按钮
    if q5 == 'y':
        print("\n  ➜ 鼠标移到【撤单】按钮上")
        input("    按Enter > ")
        mx, my = get_mouse_pos()
        result['positions']['cancel_btn'] = [mx - win_left, my - win_top]
        print(f"    ✓ 撤单按钮: 相对({mx - win_left}, {my - win_top})")
    
    # 如果有全撤按钮
    if q4 == 'y':
        print("\n  ➜ 鼠标移到【全撤】按钮上")
        input("    按Enter > ")
        mx, my = get_mouse_pos()
        result['positions']['cancel_all_btn'] = [mx - win_left, my - win_top]
        print(f"    ✓ 全撤按钮: 相对({mx - win_left}, {my - win_top})")

    # === 步骤5: 测试撤单操作 ===
    print("\n" + "─" * 50)
    print("  步骤5: 测试撤单操作")
    print("─" * 50)
    print()
    print("  现在测试实际撤单操作(会真的撤掉一笔委托!)")
    
    do_test = input("  要测试吗? (y=测试/n=跳过): ").strip().lower()
    
    if do_test == 'y':
        print()
        print("  测试方法:")
        if 'cancel_btn' in result['positions']:
            print("  A. 点击第一行选中 → 点[撤单]按钮")
        print("  B. 双击第一行")
        print()
        method = input("  用哪种? (a/b): ").strip().lower()
        
        input("  按Enter执行撤单测试 > ")
        activate(hwnd)
        time.sleep(0.2)
        
        # 先按F3确保在撤单面板
        press_key(0x72)
        time.sleep(0.5)
        
        first_row = result['positions']['first_row']
        abs_x = win_left + first_row[0]
        abs_y = win_top + first_row[1]
        
        if method == 'a' and 'cancel_btn' in result['positions']:
            # 方法A: 点击选中 → 点撤单按钮
            print(f"  点击第一行 ({abs_x}, {abs_y})...")
            click_abs(abs_x, abs_y, wait=0.5)
            
            cancel_btn = result['positions']['cancel_btn']
            btn_x = win_left + cancel_btn[0]
            btn_y = win_top + cancel_btn[1]
            print(f"  点击撤单按钮 ({btn_x}, {btn_y})...")
            click_abs(btn_x, btn_y, wait=1.0)
        else:
            # 方法B: 双击第一行
            print(f"  双击第一行 ({abs_x}, {abs_y})...")
            double_click_abs(abs_x, abs_y, wait=1.0)
        
        # 检查是否有确认弹窗
        print()
        has_confirm = input("  出现确认弹窗了吗? (y/n): ").strip().lower()
        result['notes'].append(f"撤单确认弹窗: {'有' if has_confirm=='y' else '无'}")
        
        if has_confirm == 'y':
            print("  按Enter确认弹窗...")
            input("  > ")
            press_key(0x0D)  # Enter确认
            time.sleep(0.5)
            
            # 记录确认按钮位置(如果不是用Enter确认的)
            need_click = input("  确认弹窗是按Enter关闭的还是要点按钮? (enter/click): ").strip()
            if need_click == 'click':
                print("  ➜ 鼠标移到确认弹窗的[确定]按钮上")
                input("    按Enter > ")
                mx, my = get_mouse_pos()
                result['positions']['confirm_dialog_btn'] = [mx - win_left, my - win_top]
            result['notes'].append(f"确认方式: {need_click}")
        
        # 验证撤单结果
        print()
        success = input("  撤单成功了吗?(委托从列表消失了) (y/n): ").strip().lower()
        result['notes'].append(f"撤单测试: {'成功' if success=='y' else '失败'}")
        
        if success == 'y':
            print("  ✓ 撤单测试成功!")
        else:
            print("  ✗ 撤单失败,请检查操作方式")

    # === 步骤6: 回到买入面板 ===
    print("\n" + "─" * 50)
    print("  步骤6: 回到买入面板(F1)")
    print("─" * 50)
    print("  按F1回到买入面板(恢复正常状态)")
    input("  按Enter > ")
    activate(hwnd)
    press_key(0x70)  # F1
    time.sleep(0.5)
    print("  [OK] 已切回F1")

    # === 保存结果 ===
    print("\n" + "─" * 50)
    output_file = Path(__file__).parent / "cancel_config.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"""
{'='*50}
  撤单探测完成! 保存到: {output_file}
{'='*50}

  撤单方式: {result['cancel_method']}
  关键坐标: {result['positions']}
  备注: {'; '.join(result['notes'])}
  
  撤单自动化流程:
    1. 激活xiadan
    2. 按F3切到撤单面板
    3. {'双击第一行' if 'b' in result.get('cancel_method','').lower() or not result['positions'].get('cancel_btn') else '点击行+点撤单按钮'}
    4. {'Enter确认弹窗' if '有' in str(result['notes']) else '无需确认'}
    5. 按F1切回买入面板
    
  请把结果发给我!
""")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
