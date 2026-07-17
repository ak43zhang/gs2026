"""
成交检测 - 区域监控版 (解决遍历延迟问题)

问题: 遍历所有窗口太慢,弹窗在遍历过程中出现又消失
解决: 持续监控屏幕右下角特定区域,只检测该区域的窗口变化

使用方法:
    1. 先运行脚本记录"无弹窗"时的基准状态
    2. 在华泰执行买入
    3. 脚本监控右下角区域,检测新出现的Afx窗口
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from datetime import datetime
from pathlib import Path
import json

# 屏幕右下角区域 (根据实测: 位置=(1534, 1039) 大小=365x167)
# 扩大区域以覆盖可能的偏移
MONITOR_REGION = {
    'x_min': 1400,  # 屏幕右侧
    'x_max': 1920,  # 屏幕最右
    'y_min': 750,   # 屏幕下方
    'y_max': 1250,  # 扩大范围,覆盖不同分辨率
}


def get_window_rect(hwnd):
    """获取窗口位置"""
    rect = ctypes.wintypes.RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def is_window_in_region(hwnd, region):
    """检查窗口是否在监控区域内"""
    left, top, right, bottom = get_window_rect(hwnd)
    
    # 检查窗口是否在区域内
    if right < region['x_min'] or left > region['x_max']:
        return False
    if bottom < region['y_min'] or top > region['y_max']:
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
        # 只记录Afx类窗口
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
    except:
        return []


def monitor_region_for_fill(target_code=None, timeout=30, poll_ms=50):
    """
    监控右下角区域,检测成交弹窗
    
    Args:
        target_code: 目标代码
        timeout: 超时秒数
        poll_ms: 检测间隔毫秒
        
    Returns:
        是否检测到成交
    """
    print("=" * 60)
    print("成交检测 - 区域监控版")
    print("=" * 60)
    print(f"\n  监控区域: {MONITOR_REGION}")
    print(f"  目标代码: {target_code or '任意'}")
    print(f"  超时: {timeout}秒")
    print(f"  检测间隔: {poll_ms}ms")
    print()
    
    import re
    
    # 记录基准状态
    print("  记录基准状态...")
    baseline = get_region_snapshot(MONITOR_REGION)
    print(f"  基准Afx窗口数: {len(baseline)}")
    
    for hwnd, info in baseline.items():
        print(f"    [{hwnd}] {info['class'][:40]}")
    
    print("\n  开始监控... (按Ctrl+C停止)\n")
    
    handled = set()
    start_time = time.time()
    
    try:
        while time.time() - start_time < timeout:
            # 快速获取当前状态
            current = get_region_snapshot(MONITOR_REGION)
            
            # 找出新出现的窗口
            new_hwnds = set(current.keys()) - set(baseline.keys()) - handled
            
            for hwnd in new_hwnds:
                info = current[hwnd]
                print(f"\n  [{time.time() - start_time:.1f}s] 发现新窗口!")
                print(f"    句柄: {hwnd}")
                print(f"    类名: {info['class']}")
                print(f"    标题: '{info['title']}'")
                print(f"    位置: {info['rect']}")
                
                # 获取窗口内容
                texts = get_window_texts_uia(hwnd)
                content = "\n".join(texts)
                
                print(f"    内容: {content[:200]}...")
                
                # 检查是否包含买入或成交关键词
                keywords = ["买入", "卖出", "成交", "委托"]
                has_keyword = any(kw in content for kw in keywords)
                
                if not has_keyword:
                    print(f"    ⚠️ 未找到关键词")
                    handled.add(hwnd)
                    continue
                
                print(f"    ✓ 找到关键词")
                
                # 解析代码 - 6位数字
                code_match = re.search(r'\b(\d{6})\b', content)
                if not code_match:
                    print(f"    ⚠️ 未找到6位代码")
                    handled.add(hwnd)
                    continue
                
                detected_code = code_match.group(1)
                print(f"    检测到代码: {detected_code}")
                
                # 验证目标代码
                if target_code and detected_code != target_code:
                    print(f"    代码不匹配: {detected_code} != {target_code}")
                    handled.add(hwnd)
                    continue
                
                print(f"\n  ★★★ 成交确认! ★★★")
                print(f"    代码: {detected_code}")
                
                # 提取更多信息
                price_match = re.search(r'价格[:：]\s*([\d.]+)', content)
                qty_match = re.search(r'数量[:：]\s*(\d+)', content)
                
                if price_match:
                    print(f"    成交价: {price_match.group(1)}")
                if qty_match:
                    print(f"    股数: {qty_match.group(1)}")
                
                # 尝试关闭弹窗
                try:
                    from pywinauto import Desktop
                    desktop = Desktop(backend="uia")
                    window = desktop.window(handle=hwnd)
                    ok_btn = window.child_window(title="确定", control_type="Button")
                    if ok_btn.exists(timeout=0.5):
                        ok_btn.click()
                        print("    已关闭弹窗")
                except:
                    pass
                
                return True, {
                    'hwnd': hwnd,
                    'code': detected_code,
                    'content': content,
                    'timestamp': datetime.now().isoformat(),
                }
                
                handled.add(hwnd)
            
            # 更新基准(累积模式)
            baseline.update(current)
            
            time.sleep(poll_ms / 1000)
    
    except KeyboardInterrupt:
        print("\n  用户中断")
    
    print(f"\n  监听超时 ({timeout}秒)")
    return False, None


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 区域监控版 (解决遍历延迟问题)                        ║
║                                                                  ║
║  问题: 遍历所有窗口太慢,弹窗在遍历过程中出现又消失               ║
║  解决: 只监控屏幕右下角特定区域,快速检测变化                     ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查依赖
    try:
        from pywinauto import Desktop
        print("✓ pywinauto 已安装")
    except ImportError:
        print("❌ 未安装 pywinauto")
        print("   pip install pywinauto")
        return
    
    # 输入目标代码
    target_code = input("\n  请输入要检测的债券代码(直接回车=检测任意): ").strip()
    
    input("\n  按Enter开始记录基准状态,然后去华泰执行买入...")
    
    # 开始监控
    detected, info = monitor_region_for_fill(
        target_code=target_code or None,
        timeout=30,
        poll_ms=50  # 50ms检测一次
    )
    
    # 结果
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到成交!")
        print(f"  信息: {info}")
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
    
    output_file = Path(__file__).parent / "popup_region_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")


if __name__ == '__main__':
    main()
