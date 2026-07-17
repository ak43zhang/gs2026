"""
成交弹窗探测脚本
检测xiadan.exe成交后弹出的通知窗口,记录标题/内容/类名

使用方法:
    1. 运行此脚本
    2. 在xiadan中执行一笔买入(会成交的那种)
    3. 脚本自动捕获弹窗信息

脚本会持续监控60秒内出现的新窗口,记录所有可能是成交通知的窗口
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

MONITOR_SECONDS = 120       # 监控时长(秒)
POLL_INTERVAL = 0.1         # 检测频率(秒)
KEYWORDS = ["成交", "委托", "回报", "确认", "通知", "提示"]  # 可能的弹窗标题关键词

# ==================== 工具 ====================

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
                windows[hwnd] = {
                    'title': buf.value,
                    'class': cls_buf.value,
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


# ==================== 主流程 ====================

def main():
    print(f"""
+======================================================+
|  成交弹窗探测脚本                                      |
|                                                      |
|  监控 {MONITOR_SECONDS} 秒, 捕获所有新出现的窗口             |
|  请在此期间执行一笔会成交的买入操作                     |
+======================================================+
    """)
    
    input("  准备好了按Enter开始监控 > ")
    
    # 记录启动时已有的窗口
    print(f"\n  开始监控... (共{MONITOR_SECONDS}秒)")
    print(f"  请现在去xiadan执行一笔买入(确保会成交的)")
    print(f"  脚本会自动捕获成交弹窗\n")
    
    baseline_windows = get_all_visible_windows()
    baseline_handles = set(baseline_windows.keys())
    
    detected = []  # 检测到的新窗口
    start_time = time.time()
    last_print = 0
    
    while time.time() - start_time < MONITOR_SECONDS:
        current_windows = get_all_visible_windows()
        current_handles = set(current_windows.keys())
        
        # 找到新出现的窗口
        new_handles = current_handles - baseline_handles
        
        for hwnd in new_handles:
            info = current_windows[hwnd]
            title = info['title']
            cls = info['class']
            
            # 记录这个新窗口
            entry = {
                'hwnd': hwnd,
                'title': title,
                'class': cls,
                'detected_at': datetime.now().isoformat(),
                'elapsed_seconds': round(time.time() - start_time, 1),
                'content': [],
                'is_keyword_match': any(kw in title for kw in KEYWORDS),
            }
            
            # 读取子控件文本
            try:
                child_texts = get_window_text_content(hwnd)
                entry['content'] = child_texts
            except:
                pass
            
            # 判断是否可能是成交弹窗
            all_text = title + ' '.join(t['text'] for t in entry['content'])
            entry['all_text'] = all_text
            
            detected.append(entry)
            
            # 实时打印
            marker = "★★★" if entry['is_keyword_match'] else "   "
            print(f"  {marker} [{entry['elapsed_seconds']}s] 新窗口: [{cls}] \"{title}\"")
            if entry['content']:
                for t in entry['content'][:5]:
                    print(f"        子控件: [{t['class']}] \"{t['text'][:50]}\"")
            print()
            
            # 加入baseline避免重复报告
            baseline_handles.add(hwnd)
        
        # 每10秒打印一次状态
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0 and elapsed != last_print:
            last_print = elapsed
            print(f"  ... 已监控 {elapsed}秒, 检测到 {len(detected)} 个新窗口 ...")
        
        time.sleep(POLL_INTERVAL)
    
    # === 结果汇总 ===
    print(f"\n{'='*50}")
    print(f"  监控结束! 共检测到 {len(detected)} 个新窗口")
    print(f"{'='*50}\n")
    
    if not detected:
        print("  未检测到任何新窗口!")
        print("  可能原因:")
        print("    - 你没有执行买入操作")
        print("    - 弹窗出现太快消失了(试试加长MONITOR_SECONDS)")
        print("    - 成交通知不是独立窗口(可能是xiadan内部消息)")
        return
    
    # 分析哪些可能是成交弹窗
    keyword_matches = [d for d in detected if d['is_keyword_match']]
    
    print("  关键词匹配的窗口(最可能是成交弹窗):")
    if keyword_matches:
        for d in keyword_matches:
            print(f"    ★ 标题: \"{d['title']}\"")
            print(f"      类名: {d['class']}")
            print(f"      出现时间: +{d['elapsed_seconds']}秒")
            print(f"      全部文本: \"{d['all_text'][:100]}\"")
            print()
    else:
        print("    无! 所有新窗口的标题都不含关键词")
        print("    所有检测到的窗口:")
        for d in detected:
            print(f"    - [{d['class']}] \"{d['title']}\" (+{d['elapsed_seconds']}s)")
            if d['content']:
                print(f"      内容: {[t['text'][:30] for t in d['content'][:3]]}")
    
    # 保存结果
    output_file = Path(__file__).parent / "popup_detect_result.json"
    # 移除hwnd(不可序列化为有意义的值)
    save_data = []
    for d in detected:
        d_copy = dict(d)
        d_copy['hwnd'] = str(d_copy['hwnd'])
        save_data.append(d_copy)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n  结果已保存: {output_file}")
    print(f"  请把此文件发给我!")
    
    # 给出建议
    print(f"""
  ─── 下一步 ───
  
  根据检测结果, 我需要知道:
  1. 哪个窗口是成交弹窗? (看标题和内容)
  2. 弹窗标题中是否包含证券代码? (用于匹配)
  3. 弹窗停留了多久? (是否足够100ms检测到)
  
  如果没检测到弹窗:
  - 可能成交通知是xiadan内部的消息(非独立窗口)
  - 需要换一种检测方式(如检测xiadan窗口内的子控件变化)
""")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  手动中断, 已停止监控")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
