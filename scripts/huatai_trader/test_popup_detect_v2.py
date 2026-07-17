"""
成交弹窗探测脚本 v2 - 增强版
改进:
1. 更高检测频率 (50ms)
2. 捕获所有窗口(不仅是新窗口)
3. 显示所有可见窗口列表
4. 支持手动标记弹窗

使用方法:
    1. 运行脚本
    2. 在华泰执行买入
    3. 看到弹窗后,在脚本窗口按Enter
    4. 脚本会捕获当前所有窗口,帮助识别弹窗
"""

import time
import sys
import json
import ctypes
import ctypes.wintypes
from ctypes import windll, Structure, c_long, byref, WINFUNCTYPE
from pathlib import Path
from datetime import datetime

# ==================== 配置 ====================

MONITOR_SECONDS = 60       # 监控时长(秒)
POLL_INTERVAL = 0.05      # 检测频率(秒) - 50ms
KEYWORDS = ["成交", "委托", "回报", "确认", "通知", "提示", "华泰", "xiadan"]

# ==================== 数据结构 ====================

class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]

# ==================== 窗口操作 ====================

def get_all_visible_windows():
    """获取所有可见窗口的信息"""
    windows = {}
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if windll.user32.IsWindowVisible(hwnd):
            length = windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                cls_buf = ctypes.create_unicode_buffer(256)
                windll.user32.GetClassNameW(hwnd, cls_buf, 256)
                
                # 获取窗口位置和大小
                rect = RECT()
                windll.user32.GetWindowRect(hwnd, byref(rect))
                
                windows[hwnd] = {
                    'title': buf.value,
                    'class': cls_buf.value,
                    'rect': {
                        'left': rect.left,
                        'top': rect.top,
                        'right': rect.right,
                        'bottom': rect.bottom,
                        'width': rect.right - rect.left,
                        'height': rect.bottom - rect.top,
                    }
                }
        return True
    
    windll.user32.EnumWindows(cb, 0)
    return windows


def get_window_text_content(hwnd):
    """尝试读取窗口内的所有文本(子控件)"""
    texts = []
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_child(child_hwnd, lp):
        length = windll.user32.GetWindowTextLengthW(child_hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            windll.user32.GetWindowTextW(child_hwnd, buf, length + 1)
            cls_buf = ctypes.create_unicode_buffer(256)
            windll.user32.GetClassNameW(child_hwnd, cls_buf, 256)
            texts.append({
                'text': buf.value,
                'class': cls_buf.value,
            })
        return True
    
    windll.user32.EnumChildWindows(hwnd, enum_child, 0)
    return texts


def print_window_info(windows, highlight_keywords=None):
    """打印窗口信息"""
    print(f"\n  当前可见窗口 ({len(windows)}个):")
    print(f"  {'='*80}")
    
    # 按关键词匹配排序
    sorted_items = []
    for hwnd, info in windows.items():
        title = info['title']
        cls = info['class']
        rect = info['rect']
        
        # 检查是否匹配关键词
        match_score = 0
        if highlight_keywords:
            for kw in highlight_keywords:
                if kw in title or kw in cls:
                    match_score += 1
        
        sorted_items.append((match_score, hwnd, info))
    
    # 按匹配分数降序
    sorted_items.sort(key=lambda x: -x[0])
    
    for match_score, hwnd, info in sorted_items:
        title = info['title']
        cls = info['class']
        rect = info['rect']
        
        marker = "★★★" if match_score > 0 else "   "
        print(f"  {marker} [{hwnd}] \"{title[:50]}\"")
        print(f"      类名: {cls}")
        print(f"      位置: ({rect['left']}, {rect['top']}) 大小: {rect['width']}x{rect['height']}")
        
        # 读取子控件
        try:
            child_texts = get_window_text_content(hwnd)
            if child_texts:
                for t in child_texts[:3]:
                    print(f"      子控件: [{t['class']}] \"{t['text'][:40]}\"")
        except:
            pass
        print()


def capture_snapshot(windows, label=""):
    """捕获窗口快照"""
    snapshot = {
        'timestamp': datetime.now().isoformat(),
        'label': label,
        'windows': {}
    }
    
    for hwnd, info in windows.items():
        snapshot['windows'][str(hwnd)] = {
            'title': info['title'],
            'class': info['class'],
            'rect': info['rect'],
        }
        
        # 尝试读取内容
        try:
            child_texts = get_window_text_content(hwnd)
            if child_texts:
                snapshot['windows'][str(hwnd)]['content'] = [
                    {'text': t['text'], 'class': t['class']} 
                    for t in child_texts[:5]
                ]
        except:
            pass
    
    return snapshot


# ==================== 主流程 ====================

def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交弹窗探测脚本 v2 - 增强版                                    ║
║                                                                  ║
║  改进:                                                           ║
║  • 50ms高频检测                                                  ║
║  • 显示所有窗口(不仅是新窗口)                                     ║
║  • 支持手动捕获                                                  ║
║                                                                  ║
║  使用方法:                                                       ║
║  1. 按Enter开始监控                                              ║
║  2. 在华泰执行买入                                               ║
║  3. 看到弹窗后,回到这里按Enter手动捕获                            ║
║  4. 或等待60秒自动结束                                           ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    input("  准备好后按Enter开始监控...")
    
    print(f"\n  开始监控... (共{MONITOR_SECONDS}秒)")
    print(f"  检测频率: 每{POLL_INTERVAL*1000:.0f}ms检测一次")
    print(f"  请现在去xiadan执行一笔买入(确保会成交的)")
    print(f"  看到弹窗后,回到此窗口按Enter手动捕获")
    print()
    
    # 记录启动时的窗口
    baseline_windows = get_all_visible_windows()
    print(f"  启动时已有 {len(baseline_windows)} 个可见窗口")
    print_window_info(baseline_windows, KEYWORDS)
    
    detected_new = []  # 新出现的窗口
    snapshots = []     # 手动捕获的快照
    start_time = time.time()
    last_print = 0
    
    # 非阻塞输入
    import threading
    input_received = threading.Event()
    
    def wait_input():
        input("\n  [等待] 看到弹窗后按Enter手动捕获 (或等待60秒自动结束)...")
        input_received.set()
    
    input_thread = threading.Thread(target=wait_input, daemon=True)
    input_thread.start()
    
    while time.time() - start_time < MONITOR_SECONDS:
        # 检查是否收到输入
        if input_received.is_set():
            # 手动捕获
            print("\n  [手动捕获] 正在记录当前所有窗口...")
            current_windows = get_all_visible_windows()
            snapshot = capture_snapshot(current_windows, label="manual_capture")
            snapshots.append(snapshot)
            
            print(f"\n  捕获了 {len(current_windows)} 个窗口:")
            print_window_info(current_windows, KEYWORDS)
            
            # 询问是否继续
            cont = input("\n  是否继续监控? (y/n): ").strip().lower()
            if cont != 'y':
                break
            input_received.clear()
            input_thread = threading.Thread(target=wait_input, daemon=True)
            input_thread.start()
        
        # 正常检测
        current_windows = get_all_visible_windows()
        
        # 检查新窗口
        new_handles = set(current_windows.keys()) - set(baseline_windows.keys())
        
        for hwnd in new_handles:
            info = current_windows[hwnd]
            title = info['title']
            cls = info['class']
            
            entry = {
                'hwnd': hwnd,
                'title': title,
                'class': cls,
                'rect': info['rect'],
                'detected_at': datetime.now().isoformat(),
                'elapsed_seconds': round(time.time() - start_time, 1),
                'is_keyword_match': any(kw in title for kw in KEYWORDS),
            }
            
            # 读取内容
            try:
                child_texts = get_window_text_content(hwnd)
                entry['content'] = child_texts
            except:
                pass
            
            detected_new.append(entry)
            baseline_windows[hwnd] = info  # 加入baseline避免重复
            
            # 实时打印
            marker = "★★★ 新窗口! " if entry['is_keyword_match'] else "新窗口: "
            print(f"\n  {marker}[{entry['elapsed_seconds']}s] \"{title[:50]}\"")
            print(f"      类名: {cls}")
            if entry.get('content'):
                for t in entry['content'][:2]:
                    print(f"      内容: \"{t['text'][:40]}\"")
        
        # 每10秒打印状态
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0 and elapsed != last_print:
            last_print = elapsed
            print(f"\n  ... 已监控 {elapsed}秒, 新窗口 {len(detected_new)} 个, 快照 {len(snapshots)} 个 ...")
        
        time.sleep(POLL_INTERVAL)
    
    # ========== 结果汇总 ==========
    print(f"\n\n{'='*80}")
    print(f"  监控结束!")
    print(f"{'='*80}")
    
    print(f"\n  自动检测到的新窗口: {len(detected_new)} 个")
    if detected_new:
        print("\n  关键词匹配的窗口:")
        for d in detected_new:
            if d['is_keyword_match']:
                print(f"    ★ [{d['elapsed_seconds']}s] \"{d['title']}\"")
                print(f"      类名: {d['class']}")
    
    print(f"\n  手动捕获的快照: {len(snapshots)} 次")
    
    # 保存结果
    output_file = Path(__file__).parent / "popup_detect_result_v2.json"
    result = {
        'detected_new': detected_new,
        'snapshots': snapshots,
        'baseline_count': len(baseline_windows),
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")
    
    # 分析建议
    print(f"\n{'='*80}")
    print("  分析建议:")
    print(f"{'='*80}")
    
    if not detected_new and not snapshots:
        print("\n  ⚠️ 未检测到任何新窗口,也未手动捕获")
        print("  可能原因:")
        print("    1. 弹窗不是独立窗口(可能是xiadan的子窗口)")
        print("    2. 弹窗出现时间太短(<50ms)")
        print("    3. 弹窗标题不含常见关键词")
        print("\n  建议:")
        print("    1. 重新运行,看到弹窗立即按Enter手动捕获")
        print("    2. 检查弹窗是否是xiadan内部的提示(非独立窗口)")
        print("    3. 使用Spy++或Inspect.exe查看弹窗属性")
    
    elif snapshots:
        print("\n  ✓ 已手动捕获快照")
        print("  请查看 popup_detect_result_v2.json 中的 'snapshots' 部分")
        print("  找到包含'成交'关键词的窗口,记录其标题和类名")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  手动中断")
    except Exception as e:
        print(f"\n  错误: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
