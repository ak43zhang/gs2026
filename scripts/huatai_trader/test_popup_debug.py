"""
成交检测 - 调试版

详细输出每一步的检测结果，帮助排查问题
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from datetime import datetime
from pathlib import Path
import json
import re

# 监控区域 - 屏幕右下角
MONITOR_REGION = {
    'x_min': 1400, 'x_max': 1920,
    'y_min': 750, 'y_max': 1250,  # 扩大y范围
}


def get_window_rect(hwnd):
    """获取窗口位置"""
    rect = ctypes.wintypes.RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def is_window_in_region(hwnd, region):
    """检查窗口是否在监控区域内"""
    left, top, right, bottom = get_window_rect(hwnd)
    center_x = (left + right) // 2
    center_y = (top + bottom) // 2
    
    if not (region['x_min'] <= center_x <= region['x_max']):
        return False
    if not (region['y_min'] <= center_y <= region['y_max']):
        return False
    return True


def get_window_class(hwnd):
    """获取窗口类名"""
    buf = ctypes.create_unicode_buffer(256)
    windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_text(hwnd):
    """获取窗口标题"""
    length = windll.user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def is_window_visible(hwnd):
    """检查窗口是否可见"""
    return bool(windll.user32.IsWindowVisible(hwnd))


def enum_windows_in_region(region):
    """枚举区域内的所有窗口"""
    windows = []
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if is_window_visible(hwnd):
            if is_window_in_region(hwnd, region):
                windows.append(hwnd)
        return True
    
    windll.user32.EnumWindows(cb, 0)
    return windows


def get_region_snapshot(region):
    """获取区域快照"""
    hwnds = enum_windows_in_region(region)
    snapshot = {}
    
    for hwnd in hwnds:
        cls = get_window_class(hwnd)
        if cls.startswith("Afx:"):
            snapshot[hwnd] = {
                'class': cls,
                'title': get_window_text(hwnd),
                'rect': get_window_rect(hwnd),
            }
    
    return snapshot


def get_window_texts_uia(hwnd):
    """使用UIA获取窗口文本"""
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        window = desktop.window(handle=hwnd)
        return window.texts()
    except Exception as e:
        return [f"UIA Error: {e}"]


def analyze_content(content, target_code=None):
    """详细分析内容"""
    print(f"\n  === 内容分析 ===")
    print(f"  内容长度: {len(content)}")
    print(f"  完整内容:\n{'-'*40}")
    print(content)
    print(f"{'-'*40}")
    
    # 检查关键词
    keywords = ["买入", "卖出", "成交", "委托", "价格", "数量", "证券", "代码"]
    found_keywords = [kw for kw in keywords if kw in content]
    print(f"\n  找到的关键词: {found_keywords}")
    
    # 检查是否有"买入"
    has_buy = "买入" in content
    print(f"  包含'买入': {has_buy}")
    
    # 查找所有6位数字
    codes = re.findall(r'\b(\d{6})\b', content)
    print(f"  找到的6位代码: {codes}")
    
    # 查找价格
    prices = re.findall(r'[\d.]+(?:元)?', content)
    print(f"  找到的价格/数字: {prices[:10]}")
    
    # 匹配目标代码
    if target_code and codes:
        matched = target_code in codes
        print(f"  目标代码 {target_code} 匹配: {matched}")
        return matched
    
    return bool(codes)


def monitor_with_debug(target_code=None, timeout=30, poll_ms=100):
    """带调试的监控"""
    print("=" * 60)
    print("成交检测 - 调试版")
    print("=" * 60)
    
    print(f"\n  监控区域: {MONITOR_REGION}")
    print(f"  目标代码: {target_code or '任意'}")
    print(f"  超时: {timeout}秒")
    print()
    
    # 记录基准
    print("  记录基准状态...")
    baseline = get_region_snapshot(MONITOR_REGION)
    print(f"  基准Afx窗口: {len(baseline)}")
    for hwnd, info in baseline.items():
        print(f"    [{hwnd}] {info['class'][:50]}")
    
    print("\n  开始监控... (按Ctrl+C停止)\n")
    
    handled = set()
    start_time = time.time()
    
    try:
        while time.time() - start_time < timeout:
            current = get_region_snapshot(MONITOR_REGION)
            
            # 找出新窗口
            new_hwnds = set(current.keys()) - set(baseline.keys()) - handled
            
            for hwnd in new_hwnds:
                elapsed = time.time() - start_time
                info = current[hwnd]
                
                print(f"\n{'='*60}")
                print(f"  [{elapsed:.1f}s] ★ 发现新窗口!")
                print(f"{'='*60}")
                print(f"  句柄: {hwnd}")
                print(f"  类名: {info['class']}")
                print(f"  标题: '{info['title']}'")
                print(f"  位置: {info['rect']}")
                
                # 获取内容
                texts = get_window_texts_uia(hwnd)
                content = "\n".join(texts)
                
                # 详细分析
                is_match = analyze_content(content, target_code)
                
                if is_match:
                    print(f"\n  ★★★ 成交确认! ★★★")
                    
                    # 尝试关闭
                    try:
                        from pywinauto import Desktop
                        desktop = Desktop(backend="uia")
                        window = desktop.window(handle=hwnd)
                        ok_btn = window.child_window(title="确定", control_type="Button")
                        if ok_btn.exists(timeout=0.5):
                            ok_btn.click()
                            print("  已关闭弹窗")
                    except:
                        pass
                    
                    return True, {
                        'hwnd': hwnd,
                        'content': content,
                        'timestamp': datetime.now().isoformat(),
                    }
                
                handled.add(hwnd)
            
            # 更新基准
            baseline.update(current)
            
            time.sleep(poll_ms / 1000)
    
    except KeyboardInterrupt:
        print("\n  用户中断")
    
    print(f"\n  监听超时 ({timeout}秒)")
    return False, None


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 调试版 (详细输出每一步)                              ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        from pywinauto import Desktop
        print("✓ pywinauto 已安装")
    except ImportError:
        print("❌ 未安装 pywinauto")
        return
    
    target_code = input("\n  请输入要检测的债券代码(直接回车=检测任意): ").strip()
    
    input("\n  按Enter开始记录基准,然后去华泰执行买入...")
    
    detected, info = monitor_with_debug(
        target_code=target_code or None,
        timeout=30,
        poll_ms=100
    )
    
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到成交!")
    else:
        print("  ⚠️ 未检测到成交")
    print(f"{'='*60}")
    
    # 保存
    result = {
        'timestamp': datetime.now().isoformat(),
        'target_code': target_code,
        'detected': detected,
        'info': info,
    }
    
    output_file = Path(__file__).parent / "popup_debug_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")


if __name__ == '__main__':
    main()
