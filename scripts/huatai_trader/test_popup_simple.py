"""
成交检测 - 极简版

策略: 检测到右下角新出现的Afx弹窗即认为成交
不解析内容，不验证代码

适用场景:
- 一次只操作一只股票
- 第一次弹窗=买入成交
- 第二次弹窗=卖出成交
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from datetime import datetime
from pathlib import Path
import json

# 监控区域 - 屏幕右下角
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


def enum_windows_in_region(region):
    """枚举区域内的所有窗口"""
    windows = []
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if is_window_visible(hwnd) and is_window_in_region(hwnd, region):
            windows.append(hwnd)
        return True
    windll.user32.EnumWindows(cb, 0)
    return windows


def monitor_popup_simple(timeout=30, poll_ms=50):
    """
    极简监控: 检测右下角新出现的Afx窗口即认为成交
    
    Args:
        timeout: 超时秒数
        poll_ms: 检测间隔毫秒
        
    Returns:
        是否检测到弹窗
    """
    print("=" * 60)
    print("成交检测 - 极简版")
    print("=" * 60)
    print(f"\n  策略: 检测到右下角Afx弹窗即认为成交")
    print(f"  监控区域: {MONITOR_REGION}")
    print(f"  超时: {timeout}秒")
    print(f"  检测间隔: {poll_ms}ms")
    print()
    
    # 记录基准状态
    print("  记录基准状态...")
    hwnds = enum_windows_in_region(MONITOR_REGION)
    baseline = set()
    for hwnd in hwnds:
        cls = get_window_class(hwnd)
        if cls.startswith("Afx:"):
            baseline.add(hwnd)
    print(f"  基准Afx窗口: {len(baseline)}个")
    
    print("\n  开始监控... (按Ctrl+C停止)\n")
    
    detected_count = 0
    start_time = time.time()
    
    try:
        while time.time() - start_time < timeout:
            # 获取当前状态
            hwnds = enum_windows_in_region(MONITOR_REGION)
            current = set()
            for hwnd in hwnds:
                cls = get_window_class(hwnd)
                if cls.startswith("Afx:"):
                    current.add(hwnd)
            
            # 找出新窗口
            new_hwnds = current - baseline
            
            for hwnd in new_hwnds:
                elapsed = time.time() - start_time
                cls = get_window_class(hwnd)
                left, top, right, bottom = get_window_rect(hwnd)
                width = right - left
                height = bottom - top
                
                detected_count += 1
                
                print(f"\n  [{elapsed:.1f}s] ★★★ 检测到弹窗 #{detected_count} ★★★")
                print(f"    句柄: {hwnd}")
                print(f"    类名: {cls[:50]}")
                print(f"    大小: {width}x{height}")
                print(f"    位置: ({left}, {top})")
                
                # 根据次数判断买入/卖出
                if detected_count == 1:
                    print(f"\n    → 第一次弹窗: 买入成交!")
                    return True, {
                        'type': 'buy',
                        'count': detected_count,
                        'hwnd': hwnd,
                        'class': cls,
                        'timestamp': datetime.now().isoformat(),
                    }
                else:
                    print(f"\n    → 第{detected_count}次弹窗: 卖出成交!")
                    return True, {
                        'type': 'sell',
                        'count': detected_count,
                        'hwnd': hwnd,
                        'class': cls,
                        'timestamp': datetime.now().isoformat(),
                    }
            
            # 更新基准(累积)
            baseline.update(current)
            
            time.sleep(poll_ms / 1000)
    
    except KeyboardInterrupt:
        print("\n  用户中断")
    
    print(f"\n  监听超时 ({timeout}秒)")
    return False, None


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 极简版                                               ║
║                                                                  ║
║  策略: 检测到右下角Afx弹窗即认为成交                            ║
║  不解析内容，不验证代码                                          ║
║                                                                  ║
║  适用场景:                                                       ║
║  • 一次只操作一只股票                                            ║
║  • 第一次弹窗 = 买入成交                                         ║
║  • 第二次弹窗 = 卖出成交                                         ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    input("\n  按Enter开始记录基准,然后去华泰执行买入...")
    
    detected, info = monitor_popup_simple(timeout=30, poll_ms=50)
    
    print(f"\n{'='*60}")
    if detected:
        print(f"  ✓ 检测到{'买入' if info['type']=='buy' else '卖出'}成交!")
        print(f"  信息: {info}")
    else:
        print("  ⚠️ 未检测到弹窗")
    print(f"{'='*60}")
    
    # 保存
    result = {
        'timestamp': datetime.now().isoformat(),
        'detected': detected,
        'info': info,
    }
    
    output_file = Path(__file__).parent / "popup_simple_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")


if __name__ == '__main__':
    main()
