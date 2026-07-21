"""
F3撤单界面校准脚本

使用方法:
1. 确保华泰xiadan已打开且有待撤委托
2. 运行脚本
3. 脚本会按F3打开撤单界面，抓取界面元素坐标
4. 产出: cancel_config.json

撤单流程设计:
  F3 → 打开撤单列表 → 找到目标委托 → 点击"撤单"按钮
"""

import time
import json
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from pathlib import Path
from datetime import datetime

OUTPUT_FILE = Path(__file__).parent / "cancel_config.json"

# ==================== Win32 工具 ====================

def get_window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value

def get_window_title(hwnd):
    length = windll.user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value

def get_window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    return {
        'left': rect.left, 'top': rect.top,
        'right': rect.right, 'bottom': rect.bottom,
        'width': rect.right - rect.left,
        'height': rect.bottom - rect.top,
    }

def find_xiadan_window():
    """查找xiadan主窗口"""
    result = []
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if windll.user32.IsWindowVisible(hwnd):
            cls = get_window_class(hwnd)
            title = get_window_title(hwnd)
            if 'xiadan' in title.lower() or ('Afx:' in cls and '网上股票交易' in title):
                result.append((hwnd, cls, title))
        return True
    
    windll.user32.EnumWindows(cb, 0)
    return result

def send_key(vk_code):
    """发送按键"""
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.wintypes.WORD),
            ("wScan", ctypes.wintypes.WORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]
    
    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [
            ("type", ctypes.wintypes.DWORD),
            ("_input", _INPUT),
        ]
    
    # Key down
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp._input.ki.wVk = vk_code
    windll.user32.SendInput(1, byref(inp), ctypes.sizeof(inp))
    time.sleep(0.05)
    
    # Key up
    inp._input.ki.dwFlags = KEYEVENTF_KEYUP
    windll.user32.SendInput(1, byref(inp), ctypes.sizeof(inp))

def get_foreground_hwnd():
    return windll.user32.GetForegroundWindow()

# ==================== 主逻辑 ====================

def main():
    print("""
╔══════════════════════════════════════════════╗
║  F3 撤单界面校准                              ║
╠══════════════════════════════════════════════╣
║  步骤:                                       ║
║  1. 确保华泰xiadan已打开                     ║
║  2. 确保有至少一个待撤委托                    ║
║  3. 按Enter开始                              ║
║  4. 脚本自动按F3 → 记录界面信息              ║
╚══════════════════════════════════════════════╝
    """)
    
    # 查找xiadan
    windows = find_xiadan_window()
    if not windows:
        print("  ⚠️ 未找到xiadan窗口，请确认已打开")
        print("  当前可见窗口:")
        
        @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def cb(hwnd, lp):
            if windll.user32.IsWindowVisible(hwnd):
                title = get_window_title(hwnd)
                cls = get_window_class(hwnd)
                if title and len(title) > 2:
                    print(f"    [{hwnd}] {cls[:30]} \"{title[:40]}\"")
            return True
        windll.user32.EnumWindows(cb, 0)
        return
    
    print(f"  ✅ 找到xiadan: {len(windows)}个窗口")
    for hwnd, cls, title in windows:
        rect = get_window_rect(hwnd)
        print(f"    [{hwnd}] {title[:40]} ({rect['width']}x{rect['height']})")
    
    input("\n  按Enter开始校准(会按F3)...")
    
    # 1. 记录当前状态
    print("\n  📋 按F3打开撤单界面...")
    
    # 记录按F3前的所有窗口
    before_hwnds = set()
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_before(hwnd, lp):
        if windll.user32.IsWindowVisible(hwnd):
            before_hwnds.add(hwnd)
        return True
    windll.user32.EnumWindows(enum_before, 0)
    
    # 激活xiadan窗口
    main_hwnd = windows[0][0]
    windll.user32.SetForegroundWindow(main_hwnd)
    time.sleep(0.3)
    
    # 按F3
    VK_F3 = 0x72
    send_key(VK_F3)
    time.sleep(1.0)  # 等待界面切换
    
    # 2. 检测变化
    print("  📋 检测界面变化...")
    
    after_hwnds = set()
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_after(hwnd, lp):
        if windll.user32.IsWindowVisible(hwnd):
            after_hwnds.add(hwnd)
        return True
    windll.user32.EnumWindows(enum_after, 0)
    
    new_windows = after_hwnds - before_hwnds
    fg_hwnd = get_foreground_hwnd()
    fg_cls = get_window_class(fg_hwnd)
    fg_title = get_window_title(fg_hwnd)
    fg_rect = get_window_rect(fg_hwnd)
    
    print(f"  前台窗口: [{fg_hwnd}] {fg_cls} \"{fg_title}\"")
    print(f"  大小: {fg_rect['width']}x{fg_rect['height']} @ ({fg_rect['left']},{fg_rect['top']})")
    print(f"  新出现窗口: {len(new_windows)}个")
    
    # 3. 用pywinauto获取控件详情
    print("\n  📋 获取撤单界面控件...")
    
    controls_info = []
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="win32")
        
        # 尝试获取前台窗口的控件
        try:
            fg_win = desktop.window(handle=fg_hwnd)
            children = fg_win.children()
            print(f"  子控件数: {len(children)}")
            
            for i, ctrl in enumerate(children):
                try:
                    ctrl_info = {
                        'index': i,
                        'class_name': ctrl.friendly_class_name(),
                        'text': ctrl.window_text()[:50],
                        'rect': ctrl.rectangle().mid_point(),
                    }
                    controls_info.append(ctrl_info)
                    
                    text = ctrl.window_text()[:40]
                    rect = ctrl.rectangle()
                    print(f"    [{i}] {ctrl.friendly_class_name()}: \"{text}\" @ ({rect.left},{rect.top},{rect.right},{rect.bottom})")
                except:
                    pass
        except Exception as e:
            print(f"  获取控件失败: {e}")
            
        # 也尝试UIA后端(可能看到更多控件)
        print("\n  📋 UIA后端控件...")
        try:
            desktop_uia = Desktop(backend="uia")
            fg_win_uia = desktop_uia.window(handle=fg_hwnd)
            
            # 查找表格/列表控件
            lists = fg_win_uia.children(control_type="List")
            tables = fg_win_uia.children(control_type="Table")
            buttons = fg_win_uia.descendants(control_type="Button")
            
            print(f"    List控件: {len(lists)}个")
            print(f"    Table控件: {len(tables)}个")
            print(f"    Button控件: {len(list(buttons))}个")
            
            for btn in buttons:
                try:
                    text = btn.window_text()
                    rect = btn.rectangle()
                    if text:
                        print(f"      Button: \"{text}\" @ ({rect.left},{rect.top},{rect.right},{rect.bottom})")
                except:
                    pass
                    
        except Exception as e:
            print(f"  UIA获取失败: {e}")
            
    except ImportError:
        print("  ⚠️ pywinauto未安装")
    
    # 4. 保存结果
    config = {
        'timestamp': datetime.now().isoformat(),
        'f3_key': 0x72,
        'main_hwnd': main_hwnd,
        'cancel_window': {
            'hwnd': fg_hwnd,
            'class': fg_cls,
            'title': fg_title,
            'rect': fg_rect,
        },
        'new_windows': [
            {
                'hwnd': h,
                'class': get_window_class(h),
                'title': get_window_title(h),
                'rect': get_window_rect(h),
            }
            for h in new_windows
        ],
        'controls': controls_info,
        'note': '手动补充: 撤单按钮坐标、委托列表位置',
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  💾 已保存: {OUTPUT_FILE}")
    print(f"\n  下一步: 查看输出，确认撤单按钮位置")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  ❌ 异常: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
