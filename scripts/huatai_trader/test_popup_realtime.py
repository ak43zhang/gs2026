"""
成交检测 - 实时调试版

持续运行，实时显示检测过程，帮助排查问题

使用方法:
    1. 运行脚本
    2. 观察输出
    3. 在华泰执行买入
    4. 看是否能检测到弹窗
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from datetime import datetime

# 监控区域
MONITOR_REGION = {
    'x_min': 1400, 'x_max': 1920,
    'y_min': 750, 'y_max': 1250,
}


def get_window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def is_window_in_region(hwnd, region):
    left, top, right, bottom = get_window_rect(hwnd)
    center_x = (left + right) // 2
    center_y = (top + bottom) // 2
    return (region['x_min'] <= center_x <= region['x_max'] and
            region['y_min'] <= center_y <= region['y_max'])


def get_window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def is_window_visible(hwnd):
    return bool(windll.user32.IsWindowVisible(hwnd))


def get_window_text(hwnd):
    length = windll.user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def enum_all_windows():
    """枚举所有窗口"""
    windows = []
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if is_window_visible(hwnd):
            windows.append(hwnd)
        return True
    windll.user32.EnumWindows(cb, 0)
    return windows


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 实时调试版                                           ║
║                                                                  ║
║  持续运行，实时显示检测过程                                      ║
║  按Ctrl+C停止                                                    ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    print(f"\n  监控区域: {MONITOR_REGION}")
    print(f"  检测间隔: 100ms")
    print(f"\n  请去华泰执行买入，观察输出...\n")
    
    # 记录基准
    print("  [初始化] 记录基准状态...")
    hwnds = enum_all_windows()
    baseline = {}
    for hwnd in hwnds:
        if is_window_in_region(hwnd, MONITOR_REGION):
            cls = get_window_class(hwnd)
            baseline[hwnd] = {
                'class': cls,
                'title': get_window_text(hwnd),
                'rect': get_window_rect(hwnd),
            }
    
    print(f"  [初始化] 基准窗口: {len(baseline)}个")
    for hwnd, info in list(baseline.items())[:5]:
        print(f"    [{hwnd}] {info['class'][:40]} \"{info['title'][:20]}\"")
    
    print(f"\n  开始实时监控... (按Ctrl+C停止)\n")
    
    detected_hwnds = set()
    cycle = 0
    
    try:
        while True:
            cycle += 1
            
            # 获取当前所有窗口
            hwnds = enum_all_windows()
            current = {}
            
            for hwnd in hwnds:
                if is_window_in_region(hwnd, MONITOR_REGION):
                    cls = get_window_class(hwnd)
                    current[hwnd] = {
                        'class': cls,
                        'title': get_window_text(hwnd),
                        'rect': get_window_rect(hwnd),
                    }
            
            # 找出新窗口
            new_hwnds = set(current.keys()) - set(baseline.keys()) - detected_hwnds
            
            if new_hwnds:
                print(f"\n{'='*60}")
                print(f"  [周期{cycle}] ★ 发现 {len(new_hwnds)} 个新窗口!")
                print(f"{'='*60}")
                
                for hwnd in new_hwnds:
                    info = current[hwnd]
                    left, top, right, bottom = info['rect']
                    width = right - left
                    height = bottom - top
                    
                    print(f"\n  新窗口详情:")
                    print(f"    句柄: {hwnd}")
                    print(f"    类名: {info['class']}")
                    print(f"    标题: '{info['title']}'")
                    print(f"    位置: ({left}, {top}) - ({right}, {bottom})")
                    print(f"    大小: {width}x{height}")
                    
                    # 检查是否是Afx类
                    is_afx = info['class'].startswith("Afx:")
                    print(f"    是否Afx: {is_afx}")
                    
                    # 检查大小
                    size_ok = 300 < width < 450 and 120 < height < 250
                    print(f"    大小匹配: {size_ok}")
                    
                    # 综合判断
                    if is_afx and size_ok:
                        print(f"\n  ★★★ 匹配成功! 这应该就是成交弹窗! ★★★")
                        detected_hwnds.add(hwnd)
                    else:
                        print(f"\n  ⚠️ 不匹配，加入已处理列表")
                        detected_hwnds.add(hwnd)
            
            # 每10个周期显示一次状态
            if cycle % 10 == 0:
                elapsed = cycle * 0.1
                current_count = len(current)
                print(f"  [{elapsed:.1f}s] 周期{cycle}, 当前区域窗口: {current_count}个")
            
            # 更新基准(累积)
            baseline.update(current)
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n\n  用户中断")
        print(f"\n  统计:")
        print(f"    总周期: {cycle}")
        print(f"    检测到的弹窗: {len(detected_hwnds)}个")
        print(f"    句柄列表: {detected_hwnds}")


if __name__ == '__main__':
    main()
