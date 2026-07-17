"""
成交弹窗探测 - 子窗口检测版

如果弹窗不是独立窗口,而是xiadan的子窗口,用这个脚本检测

使用方法:
    1. 运行脚本
    2. 在华泰执行买入
    3. 看到弹窗后,回到脚本按Enter
    4. 脚本会列出xiadan的所有子窗口
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, Structure, c_long, byref, WINFUNCTYPE
from datetime import datetime
from pathlib import Path

XIADAN_TITLE = "网上股票交易系统5.0"


def find_window(title):
    """查找窗口"""
    found = []
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if windll.user32.IsWindowVisible(hwnd):
            length = windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                if title in buf.value:
                    found.append(hwnd)
        return True
    windll.user32.EnumWindows(cb, 0)
    return found[0] if found else None


def get_child_windows(parent_hwnd):
    """获取所有子窗口"""
    children = []
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        length = windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1) if length > 0 else ctypes.create_unicode_buffer(1)
        if length > 0:
            windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        
        cls_buf = ctypes.create_unicode_buffer(256)
        windll.user32.GetClassNameW(hwnd, cls_buf, 256)
        
        # 获取窗口矩形
        rect = ctypes.wintypes.RECT()
        windll.user32.GetWindowRect(hwnd, byref(rect))
        
        children.append({
            'hwnd': hwnd,
            'title': buf.value,
            'class': cls_buf.value,
            'rect': {
                'left': rect.left,
                'top': rect.top,
                'right': rect.right,
                'bottom': rect.bottom,
            }
        })
        return True
    
    windll.user32.EnumChildWindows(parent_hwnd, cb, 0)
    return children


def get_all_descendants(parent_hwnd, depth=0, max_depth=5):
    """递归获取所有后代窗口"""
    if depth > max_depth:
        return []
    
    result = []
    children = get_child_windows(parent_hwnd)
    
    for child in children:
        child['depth'] = depth
        result.append(child)
        # 递归获取子窗口
        descendants = get_all_descendants(child['hwnd'], depth + 1, max_depth)
        result.extend(descendants)
    
    return result


def print_window_tree(windows, keywords=None, indent=0):
    """打印窗口树"""
    for w in windows:
        title = w['title']
        cls = w['class']
        depth = w.get('depth', 0)
        prefix = "  " * depth
        
        # 检查关键词
        match = False
        if keywords:
            for kw in keywords:
                if kw in title or kw in cls:
                    match = True
                    break
        
        marker = "★ " if match else "  "
        print(f"{prefix}{marker}[{w['hwnd']}] \"{title[:40]}\"")
        print(f"{prefix}   类名: {cls}")


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交弹窗探测 - 子窗口检测版                                      ║
║                                                                  ║
║  如果弹窗不是独立窗口,而是xiadan的子窗口,用这个脚本               ║
║                                                                  ║
║  使用方法:                                                       ║
║  1. 运行脚本                                                      ║
║  2. 在华泰执行买入                                               ║
║  3. 看到弹窗后,回到脚本按Enter                                   ║
║  4. 脚本会列出xiadan的所有子窗口                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 查找xiadan主窗口
    print(f"  查找 '{XIADAN_TITLE}'...")
    xiadan_hwnd = find_window(XIADAN_TITLE)
    
    if not xiadan_hwnd:
        print(f"  ❌ 未找到 '{XIADAN_TITLE}'")
        print("  请确保华泰软件已打开")
        return
    
    print(f"  ✓ 找到主窗口: {xiadan_hwnd}")
    
    # 获取初始状态
    print("\n  正在记录初始子窗口状态...")
    baseline = get_all_descendants(xiadan_hwnd)
    print(f"  初始子窗口数量: {len(baseline)}")
    
    print("\n  初始子窗口列表:")
    print_window_tree(baseline, keywords=["成交", "委托", "回报", "确认", "提示"])
    
    # 等待用户执行买入
    input("\n  请去华泰执行一笔买入,看到弹窗后按Enter...")
    
    # 获取当前状态
    print("\n  正在记录当前子窗口状态...")
    current = get_all_descendants(xiadan_hwnd)
    print(f"  当前子窗口数量: {len(current)}")
    
    # 找出新出现的子窗口
    baseline_handles = {w['hwnd'] for w in baseline}
    new_windows = [w for w in current if w['hwnd'] not in baseline_handles]
    
    print(f"\n  新出现的子窗口: {len(new_windows)} 个")
    
    if new_windows:
        print("\n  新窗口详情:")
        print_window_tree(new_windows, keywords=["成交", "委托", "回报", "确认", "提示"])
        
        # 保存结果
        import json
        result = {
            'timestamp': datetime.now().isoformat(),
            'xiadan_hwnd': xiadan_hwnd,
            'baseline_count': len(baseline),
            'current_count': len(current),
            'new_windows': new_windows,
        }
        
        output_file = Path(__file__).parent / "popup_child_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"\n  结果已保存: {output_file}")
        
        # 分析
        print("\n  分析:")
        for w in new_windows:
            title = w['title']
            cls = w['class']
            if any(kw in title for kw in ["成交", "委托", "回报"]):
                print(f"    ✓ 可能是成交弹窗:")
                print(f"      标题: {title}")
                print(f"      类名: {cls}")
                print(f"      位置: ({w['rect']['left']}, {w['rect']['top']})")
    else:
        print("\n  ⚠️ 未检测到新子窗口")
        print("  可能原因:")
        print("    1. 弹窗不是子窗口(可能是独立窗口)")
        print("    2. 弹窗已经消失")
        print("    3. 弹窗是系统级别的(非xiadan子窗口)")
        print("\n  建议:")
        print("    1. 使用 test_popup_detect_v2.py 检测独立窗口")
        print("    2. 使用 Spy++ 查看窗口层次结构")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  错误: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
