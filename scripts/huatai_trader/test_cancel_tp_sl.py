"""
条件单终止界面校准脚本

流程: 打开条件单界面 → 我的条件单 → 全选 → 终止
使用方法:
  1. 确保xiadan已打开，且有至少一个条件单在监控中
  2. 手动打开条件单界面(到"我的条件单-当前监控中"页面)
  3. 运行脚本，脚本会抓取界面元素坐标
  4. 产出: tp_sl_cancel_config.json
"""

import time
import json
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from pathlib import Path
from datetime import datetime

OUTPUT_FILE = Path(__file__).parent / "tp_sl_cancel_config.json"


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


def main():
    print("""
╔══════════════════════════════════════════════════╗
║  条件单终止界面校准                                ║
╠══════════════════════════════════════════════════╣
║  前置条件:                                        ║
║  1. xiadan已打开                                  ║
║  2. 手动打开到"我的条件单 - 当前监控中"页面          ║
║  3. 确保界面上有条件单记录(否则看不到全选/终止)       ║
║                                                   ║
║  脚本会用pywinauto抓取当前界面的控件坐标            ║
╚══════════════════════════════════════════════════╝
    """)
    
    input("  确认已打开条件单管理界面后，按Enter开始...")
    
    # 获取前台窗口
    fg_hwnd = windll.user32.GetForegroundWindow()
    fg_cls = get_window_class(fg_hwnd)
    fg_title = get_window_title(fg_hwnd)
    fg_rect = get_window_rect(fg_hwnd)
    
    print(f"\n  前台窗口: [{fg_hwnd}] {fg_cls}")
    print(f"  标题: \"{fg_title}\"")
    print(f"  大小: {fg_rect['width']}x{fg_rect['height']} @ ({fg_rect['left']},{fg_rect['top']})")
    
    # 用pywinauto获取控件
    print("\n  📋 抓取控件...")
    
    controls_info = []
    buttons_found = []
    checkboxes_found = []
    
    try:
        from pywinauto import Desktop
        
        # Win32后端
        print("\n  [Win32后端]")
        desktop = Desktop(backend="win32")
        try:
            fg_win = desktop.window(handle=fg_hwnd)
            children = fg_win.children()
            print(f"  子控件数: {len(children)}")
            
            for i, ctrl in enumerate(children):
                try:
                    cls_name = ctrl.friendly_class_name()
                    text = ctrl.window_text()[:60]
                    rect = ctrl.rectangle()
                    mid = rect.mid_point()
                    
                    info = {
                        'index': i,
                        'class': cls_name,
                        'text': text,
                        'mid_x': mid.x if hasattr(mid, 'x') else mid[0],
                        'mid_y': mid.y if hasattr(mid, 'y') else mid[1],
                        'rect': f"({rect.left},{rect.top},{rect.right},{rect.bottom})",
                    }
                    controls_info.append(info)
                    
                    # 识别关键控件
                    if 'Button' in cls_name or 'button' in cls_name.lower():
                        buttons_found.append(info)
                    if '全选' in text or '终止' in text or '删除' in text or '暂停' in text:
                        buttons_found.append(info)
                    if 'Check' in cls_name:
                        checkboxes_found.append(info)
                    
                    if text:
                        print(f"    [{i}] {cls_name}: \"{text}\" @ mid({info['mid_x']},{info['mid_y']})")
                except:
                    pass
        except Exception as e:
            print(f"  Win32失败: {e}")
        
        # UIA后端(可能看到更多)
        print("\n  [UIA后端]")
        try:
            desktop_uia = Desktop(backend="uia")
            fg_win_uia = desktop_uia.window(handle=fg_hwnd)
            
            # 找按钮
            buttons = list(fg_win_uia.descendants(control_type="Button"))
            checks = list(fg_win_uia.descendants(control_type="CheckBox"))
            tabs = list(fg_win_uia.descendants(control_type="TabItem"))
            
            print(f"    Button: {len(buttons)}个")
            for btn in buttons:
                try:
                    text = btn.window_text()
                    rect = btn.rectangle()
                    mid = rect.mid_point()
                    mid_x = mid.x if hasattr(mid, 'x') else mid[0]
                    mid_y = mid.y if hasattr(mid, 'y') else mid[1]
                    if text:
                        print(f"      \"{text}\" @ mid({mid_x},{mid_y}) rect({rect.left},{rect.top},{rect.right},{rect.bottom})")
                        buttons_found.append({'text': text, 'mid_x': mid_x, 'mid_y': mid_y})
                except:
                    pass
            
            print(f"    CheckBox: {len(checks)}个")
            for chk in checks:
                try:
                    text = chk.window_text()
                    rect = chk.rectangle()
                    mid = rect.mid_point()
                    mid_x = mid.x if hasattr(mid, 'x') else mid[0]
                    mid_y = mid.y if hasattr(mid, 'y') else mid[1]
                    print(f"      \"{text}\" @ mid({mid_x},{mid_y})")
                    checkboxes_found.append({'text': text, 'mid_x': mid_x, 'mid_y': mid_y})
                except:
                    pass
            
            print(f"    TabItem: {len(tabs)}个")
            for tab in tabs:
                try:
                    text = tab.window_text()
                    rect = tab.rectangle()
                    mid = rect.mid_point()
                    mid_x = mid.x if hasattr(mid, 'x') else mid[0]
                    mid_y = mid.y if hasattr(mid, 'y') else mid[1]
                    print(f"      \"{text}\" @ mid({mid_x},{mid_y})")
                except:
                    pass
                    
        except Exception as e:
            print(f"  UIA失败: {e}")
            
    except ImportError:
        print("  ⚠️ pywinauto未安装")
    
    # 保存结果
    config = {
        'timestamp': datetime.now().isoformat(),
        'window': {
            'hwnd': fg_hwnd,
            'class': fg_cls,
            'title': fg_title,
            'rect': fg_rect,
        },
        'buttons': buttons_found,
        'checkboxes': checkboxes_found,
        'all_controls': controls_info[:50],
        'note': '需要确认: 全选按钮坐标, 终止按钮坐标',
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  💾 已保存: {OUTPUT_FILE}")
    
    # 显示关键信息
    print(f"\n{'='*50}")
    print(f"  关键按钮:")
    print(f"{'='*50}")
    for btn in buttons_found:
        text = btn.get('text', '')
        if any(k in text for k in ['全选', '终止', '删除', '暂停', '全部']):
            print(f"  🔴 {text} @ ({btn['mid_x']}, {btn['mid_y']})")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  ❌ 异常: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
