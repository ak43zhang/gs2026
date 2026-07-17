"""
成交检测 - xiadan内部消息版

如果弹窗是xiadan内部的消息提示(非独立窗口),用这个脚本
通过监控xiadan窗口内的文本变化来判断是否成交

使用方法:
    1. 运行脚本
    2. 在华泰执行买入
    3. 脚本自动检测xiadan窗口内的文本变化
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from datetime import datetime
from pathlib import Path
import json

XIADAN_TITLE = "网上股票交易系统5.0"


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), 
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


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


def get_window_text(hwnd):
    """获取窗口文本"""
    length = windll.user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_all_child_texts(hwnd):
    """递归获取所有子控件的文本"""
    texts = []
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(child_hwnd, lp):
        # 获取文本
        text_len = windll.user32.GetWindowTextLengthW(child_hwnd)
        if text_len > 0:
            buf = ctypes.create_unicode_buffer(text_len + 1)
            windll.user32.GetWindowTextW(child_hwnd, buf, text_len + 1)
            if buf.value.strip():
                texts.append(buf.value.strip())
        return True
    
    windll.user32.EnumChildWindows(hwnd, cb, 0)
    return texts


def get_all_texts_recursive(hwnd, depth=0, max_depth=3):
    """递归获取所有文本"""
    if depth > max_depth:
        return []
    
    all_texts = []
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(child_hwnd, lp):
        # 获取文本
        text_len = windll.user32.GetWindowTextLengthW(child_hwnd)
        if text_len > 0:
            buf = ctypes.create_unicode_buffer(text_len + 1)
            windll.user32.GetWindowTextW(child_hwnd, buf, text_len + 1)
            text = buf.value.strip()
            if text:
                all_texts.append({
                    'hwnd': child_hwnd,
                    'text': text,
                    'depth': depth,
                })
                # 递归获取子控件
                if depth < max_depth:
                    sub_texts = get_all_texts_recursive(child_hwnd, depth + 1, max_depth)
                    all_texts.extend(sub_texts)
        return True
    
    windll.user32.EnumChildWindows(hwnd, cb, 0)
    return all_texts


def find_text_changes(before, after, keywords=["成交", "委托", "成功", "买入"]):
    """找出文本变化"""
    before_set = {item['text'] for item in before}
    after_set = {item['text'] for item in after}
    
    # 新增的文本
    new_texts = after_set - before_set
    
    # 消失的文本
    removed_texts = before_set - after_set
    
    # 匹配关键词的新文本
    matched = [t for t in new_texts if any(kw in t for kw in keywords)]
    
    return {
        'new': list(new_texts),
        'removed': list(removed_texts),
        'matched': matched,
    }


def monitor_xiadan_for_fill(xiadan_hwnd, timeout=30, poll_interval=0.1):
    """
    监控xiadan窗口内的文本变化,检测成交
    
    Args:
        xiadan_hwnd: xiadan主窗口句柄
        timeout: 监控超时(秒)
        poll_interval: 检测间隔(秒)
        
    Returns:
        是否检测到成交
    """
    print(f"  开始监控xiadan内部文本变化...")
    print(f"  超时: {timeout}秒, 检测间隔: {poll_interval*1000:.0f}ms")
    
    # 记录初始状态
    baseline = get_all_texts_recursive(xiadan_hwnd)
    print(f"  初始文本数量: {len(baseline)}")
    
    start_time = time.time()
    detected = False
    detection_info = None
    
    while time.time() - start_time < timeout:
        # 获取当前状态
        current = get_all_texts_recursive(xiadan_hwnd)
        
        # 对比变化
        changes = find_text_changes(baseline, current)
        
        if changes['new']:
            print(f"\n  [{time.time() - start_time:.1f}s] 检测到新文本:")
            for t in changes['new']:
                marker = "★" if any(kw in t for kw in ["成交", "委托", "成功"]) else " "
                print(f"    {marker} \"{t[:80]}\"")
            
            if changes['matched']:
                print(f"\n  ✓ 匹配到关键词!")
                for t in changes['matched']:
                    print(f"    → \"{t}\"")
                detected = True
                detection_info = changes
                break
        
        # 更新baseline(累积检测)
        baseline = current
        
        time.sleep(poll_interval)
    
    return detected, detection_info


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - xiadan内部消息版                                      ║
║                                                                  ║
║  通过监控xiadan窗口内的文本变化来判断是否成交                     ║
║  适用于: 弹窗是xiadan内部消息提示(非独立窗口)                     ║
║                                                                  ║
║  使用方法:                                                       ║
║  1. 运行脚本                                                      ║
║  2. 在华泰执行买入                                               ║
║  3. 脚本自动检测文本变化                                          ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 查找xiadan
    print(f"  查找 '{XIADAN_TITLE}'...")
    xiadan_hwnd = find_window(XIADAN_TITLE)
    
    if not xiadan_hwnd:
        print(f"  ❌ 未找到 '{XIADAN_TITLE}'")
        print("  请确保华泰软件已打开")
        return
    
    print(f"  ✓ 找到主窗口: {xiadan_hwnd}")
    
    # 显示初始文本样本
    print("\n  当前窗口内的文本样本:")
    sample = get_all_texts_recursive(xiadan_hwnd)
    for item in sample[:10]:
        text = item['text']
        if len(text) > 5:  # 过滤短文本
            print(f"    \"{text[:60]}\"")
    
    input("\n  请去华泰执行一笔买入,按Enter开始监控...")
    
    # 开始监控
    detected, info = monitor_xiadan_for_fill(xiadan_hwnd, timeout=30)
    
    # 结果
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到成交!")
        print(f"  匹配的文本: {info['matched']}")
    else:
        print("  ⚠️ 未检测到成交(30秒超时)")
    print(f"{'='*60}")
    
    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'detected': detected,
        'info': info,
        'xiadan_hwnd': xiadan_hwnd,
    }
    
    output_file = Path(__file__).parent / "popup_internal_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")
    
    # 建议
    if detected:
        print("\n  下一步:")
        print("  1. 查看结果文件中的匹配文本")
        print("  2. 提取关键词用于自动检测")
        print("  3. 更新 auto_trader.py 中的检测逻辑")
    else:
        print("\n  可能原因:")
        print("    1. 买入未成交(价格不合适)")
        print("    2. 成交提示太快消失")
        print("    3. 成交提示在xiadan的其他子窗口中")
        print("\n  建议:")
        print("    1. 确保买入价格合适,能立即成交")
        print("    2. 使用录屏软件观察弹窗出现时机")
        print("    3. 尝试使用Spy++查看窗口消息")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  错误: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
