"""
成交检测 - 高敏感版

策略: 检测任何变化，不只是新窗口
包括:
- 新窗口出现
- 窗口大小变化
- 窗口位置变化
- 窗口从隐藏变可见
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from datetime import datetime

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


def get_window_text(hwnd):
    length = windll.user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def enum_windows():
    windows = []
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if is_visible(hwnd) and is_in_region(hwnd):
            windows.append(hwnd)
        return True
    windll.user32.EnumWindows(cb, 0)
    return windows


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 高敏感版                                             ║
║                                                                  ║
║  检测任何变化:                                                   ║
║  • 新窗口出现                                                    ║
║  • 窗口大小变化                                                  ║
║  • 窗口位置变化                                                  ║
║  • 窗口从隐藏变可见                                              ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    print(f"\n  监控区域: {MONITOR_REGION}")
    print(f"\n  请去华泰执行买入...\n")
    
    # 初始状态
    print("  [初始化] 记录初始状态...")
    hwnds = enum_windows()
    prev_state = {}
    for hwnd in hwnds:
        cls = get_window_class(hwnd)
        left, top, right, bottom = get_window_rect(hwnd)
        prev_state[hwnd] = {
            'class': cls,
            'title': get_window_text(hwnd),
            'rect': (left, top, right, bottom),
            'width': right - left,
            'height': bottom - top,
        }
    
    print(f"  [初始化] 初始窗口: {len(prev_state)}个")
    
    detected = []
    cycle = 0
    
    try:
        while True:
            cycle += 1
            time.sleep(0.05)  # 50ms检测
            
            # 获取当前状态
            hwnds = enum_windows()
            curr_state = {}
            for hwnd in hwnds:
                cls = get_window_class(hwnd)
                left, top, right, bottom = get_window_rect(hwnd)
                curr_state[hwnd] = {
                    'class': cls,
                    'title': get_window_text(hwnd),
                    'rect': (left, top, right, bottom),
                    'width': right - left,
                    'height': bottom - top,
                }
            
            # 检测变化
            changes = []
            
            # 1. 新窗口
            for hwnd in curr_state:
                if hwnd not in prev_state:
                    info = curr_state[hwnd]
                    changes.append({
                        'type': 'new',
                        'hwnd': hwnd,
                        'info': info,
                    })
            
            # 2. 大小变化
            for hwnd in curr_state:
                if hwnd in prev_state:
                    curr = curr_state[hwnd]
                    prev = prev_state[hwnd]
                    if abs(curr['width'] - prev['width']) > 10 or abs(curr['height'] - prev['height']) > 10:
                        changes.append({
                            'type': 'resize',
                            'hwnd': hwnd,
                            'info': curr,
                            'old_size': (prev['width'], prev['height']),
                            'new_size': (curr['width'], curr['height']),
                        })
            
            # 3. 位置变化
            for hwnd in curr_state:
                if hwnd in prev_state:
                    curr = curr_state[hwnd]
                    prev = prev_state[hwnd]
                    curr_pos = (curr['rect'][0], curr['rect'][1])
                    prev_pos = (prev['rect'][0], prev['rect'][1])
                    if abs(curr_pos[0] - prev_pos[0]) > 10 or abs(curr_pos[1] - prev_pos[1]) > 10:
                        changes.append({
                            'type': 'move',
                            'hwnd': hwnd,
                            'info': curr,
                            'old_pos': prev_pos,
                            'new_pos': curr_pos,
                        })
            
            # 显示变化
            if changes:
                print(f"\n{'='*60}")
                print(f"  [周期{cycle}] 检测到 {len(changes)} 个变化!")
                print(f"{'='*60}")
                
                for change in changes:
                    print(f"\n  变化类型: {change['type']}")
                    print(f"    句柄: {change['hwnd']}")
                    print(f"    类名: {change['info']['class']}")
                    print(f"    标题: '{change['info']['title']}'")
                    print(f"    大小: {change['info']['width']}x{change['info']['height']}")
                    
                    if change['type'] == 'resize':
                        print(f"    大小变化: {change['old_size']} -> {change['new_size']}")
                    if change['type'] == 'move':
                        print(f"    位置变化: {change['old_pos']} -> {change['new_pos']}")
                    
                    # 检查是否是Afx弹窗
                    is_afx = change['info']['class'].startswith('Afx:')
                    is_popup_size = 300 < change['info']['width'] < 450 and 120 < change['info']['height'] < 250
                    
                    if is_afx and is_popup_size:
                        print(f"\n    ★★★ 可能是成交弹窗! ★★★")
                        detected.append(change)
            
            # 更新状态
            prev_state = curr_state
    
    except KeyboardInterrupt:
        print("\n\n  停止")
        print(f"\n  检测到 {len(detected)} 个可能的弹窗")


if __name__ == '__main__':
    main()
