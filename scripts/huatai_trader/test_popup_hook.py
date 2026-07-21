"""
成交弹窗探测 - WinEvent Hook 版 (事件驱动, 不漏窗口)

原理: 使用 SetWinEventHook 监听 EVENT_OBJECT_SHOW 事件
     窗口出现的瞬间触发回调, 比轮询可靠得多

使用方法:
    1. 运行脚本
    2. 在华泰xiadan中执行一笔真实交易(确保能成交)
    3. 脚本会捕获所有新出现的窗口
    4. 120秒后自动结束, 或按Ctrl+C手动结束

产出: popup_hook_result.json (所有捕获的窗口事件)
"""

import time
import json
import ctypes
import ctypes.wintypes
import threading
import os
from ctypes import windll, byref, WINFUNCTYPE, POINTER, Structure
from ctypes.wintypes import (
    HWND, DWORD, LONG, HANDLE, UINT, WPARAM, LPARAM, BOOL, RECT
)
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# ==================== 常量 ====================

# WinEvent 常量
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_SHOW = 0x8002
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_FOCUS = 0x8005
EVENT_OBJECT_LOCATIONCHANGE = 0x800B

WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

OBJID_WINDOW = 0
CHILDID_SELF = 0

# 监控时长
MONITOR_SECONDS = 120

# 输出文件
OUTPUT_FILE = Path(__file__).parent / "popup_hook_result.json"

# ==================== 数据收集 ====================

# 全局收集器
events_log = []           # 所有事件
new_windows_log = []      # 新出现的窗口(去重)
seen_hwnds = set()        # 已见过的句柄
baseline_hwnds = set()    # 基准窗口集合
start_time = None
monitor_active = True

# 锁
log_lock = threading.Lock()


# ==================== Win32 工具函数 ====================

def get_window_class(hwnd):
    """获取窗口类名"""
    try:
        buf = ctypes.create_unicode_buffer(256)
        windll.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    except:
        return ""


def get_window_title(hwnd):
    """获取窗口标题"""
    try:
        length = windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except:
        return ""


def get_window_rect_info(hwnd):
    """获取窗口位置和大小"""
    try:
        rect = ctypes.wintypes.RECT()
        windll.user32.GetWindowRect(hwnd, byref(rect))
        return {
            'left': rect.left,
            'top': rect.top,
            'right': rect.right,
            'bottom': rect.bottom,
            'width': rect.right - rect.left,
            'height': rect.bottom - rect.top,
            'center_x': (rect.left + rect.right) // 2,
            'center_y': (rect.top + rect.bottom) // 2,
        }
    except:
        return None


def get_window_pid(hwnd):
    """获取窗口所属进程ID"""
    try:
        pid = ctypes.wintypes.DWORD()
        windll.user32.GetWindowThreadProcessId(hwnd, byref(pid))
        return pid.value
    except:
        return 0


def get_process_name(pid):
    """获取进程名"""
    try:
        import psutil
        p = psutil.Process(pid)
        return p.name()
    except:
        # 回退: 使用 kernel32
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                buf = ctypes.create_unicode_buffer(260)
                size = ctypes.wintypes.DWORD(260)
                windll.kernel32.QueryFullProcessImageNameW(handle, 0, buf, byref(size))
                windll.kernel32.CloseHandle(handle)
                return os.path.basename(buf.value)
        except:
            pass
        return f"pid_{pid}"


def get_parent_window(hwnd):
    """获取父窗口"""
    try:
        parent = windll.user32.GetParent(hwnd)
        return parent if parent else None
    except:
        return None


def is_window_visible(hwnd):
    """检查窗口是否可见"""
    try:
        return bool(windll.user32.IsWindowVisible(hwnd))
    except:
        return False


def get_window_style(hwnd):
    """获取窗口样式"""
    try:
        GWL_STYLE = -16
        GWL_EXSTYLE = -20
        style = windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        ex_style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        return {'style': hex(style), 'ex_style': hex(ex_style)}
    except:
        return {}


def get_child_texts(hwnd, max_children=10):
    """获取子控件文本"""
    texts = []
    count = [0]
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_child(child_hwnd, lp):
        if count[0] >= max_children:
            return False
        length = windll.user32.GetWindowTextLengthW(child_hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            windll.user32.GetWindowTextW(child_hwnd, buf, length + 1)
            cls_buf = ctypes.create_unicode_buffer(256)
            windll.user32.GetClassNameW(child_hwnd, cls_buf, 256)
            texts.append({
                'text': buf.value,
                'class': cls_buf.value,
                'hwnd': child_hwnd,
            })
            count[0] += 1
        return True
    
    try:
        windll.user32.EnumChildWindows(hwnd, enum_child, 0)
    except:
        pass
    return texts


def capture_full_window_info(hwnd):
    """捕获窗口完整信息"""
    info = {
        'hwnd': hwnd,
        'class_name': get_window_class(hwnd),
        'title': get_window_title(hwnd),
        'rect': get_window_rect_info(hwnd),
        'visible': is_window_visible(hwnd),
        'pid': get_window_pid(hwnd),
        'process_name': '',
        'parent_hwnd': get_parent_window(hwnd),
        'styles': get_window_style(hwnd),
        'child_texts': [],
        'timestamp': datetime.now().isoformat(),
        'elapsed_ms': int((time.time() - start_time) * 1000) if start_time else 0,
    }
    
    # 获取进程名
    if info['pid']:
        info['process_name'] = get_process_name(info['pid'])
    
    # 获取父窗口信息
    if info['parent_hwnd']:
        info['parent_class'] = get_window_class(info['parent_hwnd'])
        info['parent_title'] = get_window_title(info['parent_hwnd'])
    
    # 获取子控件文本
    info['child_texts'] = get_child_texts(hwnd)
    
    return info


# ==================== 截图功能 ====================

def take_screenshot(hwnd, filename):
    """截取屏幕区域(窗口附近)"""
    try:
        from PIL import ImageGrab
        rect = get_window_rect_info(hwnd)
        if rect:
            # 扩大区域截图
            margin = 50
            bbox = (
                max(0, rect['left'] - margin),
                max(0, rect['top'] - margin),
                rect['right'] + margin,
                rect['bottom'] + margin,
            )
            img = ImageGrab.grab(bbox)
            screenshots_dir = Path(__file__).parent / "popup_screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            img.save(screenshots_dir / filename)
            return str(screenshots_dir / filename)
    except Exception as e:
        pass
    return None


# ==================== WinEvent Hook ====================

# 回调函数类型
WinEventProcType = WINFUNCTYPE(
    None,           # 返回值
    HANDLE,         # hWinEventHook
    DWORD,          # event
    HWND,           # hwnd
    LONG,           # idObject
    LONG,           # idChild
    DWORD,          # idEventThread
    DWORD,          # dwmsEventTime
)


def win_event_callback(hWinEventHook, event, hwnd, idObject, idChild, 
                       idEventThread, dwmsEventTime):
    """WinEvent 回调 - 窗口事件触发时调用"""
    global monitor_active
    
    if not monitor_active:
        return
    
    # 只关心窗口级事件
    if idObject != OBJID_WINDOW or idChild != CHILDID_SELF:
        return
    
    if not hwnd:
        return
    
    # 跳过已见过的(SHOW事件可能重复触发)
    if hwnd in baseline_hwnds:
        return
    
    # 检查可见性
    if not is_window_visible(hwnd):
        return
    
    elapsed_ms = int((time.time() - start_time) * 1000) if start_time else 0
    
    # 事件类型
    event_names = {
        EVENT_OBJECT_CREATE: "CREATE",
        EVENT_OBJECT_SHOW: "SHOW",
        EVENT_SYSTEM_FOREGROUND: "FOREGROUND",
        EVENT_OBJECT_FOCUS: "FOCUS",
    }
    event_name = event_names.get(event, f"0x{event:04X}")
    
    # 快速获取基本信息
    cls = get_window_class(hwnd)
    title = get_window_title(hwnd)
    
    # 过滤: 忽略一些明显无关的窗口
    IGNORE_CLASSES = {
        "tooltips_class32", "msctls_statusbar32", 
        "SysShadow", "WorkerW", "Progman",
    }
    if cls.lower() in {c.lower() for c in IGNORE_CLASSES}:
        return
    
    with log_lock:
        # 记录事件
        event_entry = {
            'event': event_name,
            'hwnd': hwnd,
            'class': cls,
            'title': title[:100],
            'elapsed_ms': elapsed_ms,
            'timestamp': datetime.now().isoformat(),
        }
        events_log.append(event_entry)
        
        # 如果是新窗口(SHOW事件 + 之前没见过)
        if hwnd not in seen_hwnds:
            seen_hwnds.add(hwnd)
            
            # 捕获完整信息
            full_info = capture_full_window_info(hwnd)
            full_info['trigger_event'] = event_name
            new_windows_log.append(full_info)
            
            # 判断是否可能是成交弹窗
            is_candidate = False
            reasons = []
            
            # 条件1: Afx类名
            if cls.startswith("Afx:"):
                is_candidate = True
                reasons.append("Afx类名")
            
            # 条件2: 右下角位置
            rect = full_info.get('rect')
            if rect and rect['center_x'] > 1400 and rect['center_y'] > 750:
                reasons.append("右下角位置")
                is_candidate = True
            
            # 条件3: 特定大小范围
            if rect and 300 < rect.get('width', 0) < 450 and 100 < rect.get('height', 0) < 250:
                reasons.append("大小匹配(300-450 x 100-250)")
            
            # 条件4: 来自xiadan进程
            if 'xiadan' in full_info.get('process_name', '').lower():
                reasons.append("xiadan进程")
                is_candidate = True
            
            # 条件5: 标题/内容包含关键词
            keywords = ["成交", "委托", "回报", "确认", "买入", "卖出"]
            content_all = title + " ".join(t.get('text', '') for t in full_info.get('child_texts', []))
            for kw in keywords:
                if kw in content_all:
                    reasons.append(f"关键词'{kw}'")
                    is_candidate = True
                    break
            
            full_info['is_candidate'] = is_candidate
            full_info['candidate_reasons'] = reasons
            
            # 控制台输出
            marker = "🔴 候选!" if is_candidate else "⚪"
            print(f"\n  {marker} [{elapsed_ms}ms] {event_name} 新窗口:")
            print(f"      句柄: {hwnd}")
            print(f"      类名: {cls}")
            print(f"      标题: '{title[:60]}'")
            if rect:
                print(f"      位置: ({rect['left']},{rect['top']}) 大小: {rect['width']}x{rect['height']}")
            print(f"      进程: {full_info.get('process_name', '?')} (PID={full_info.get('pid', '?')})")
            if full_info.get('child_texts'):
                print(f"      子控件: {[t['text'][:30] for t in full_info['child_texts'][:5]]}")
            if reasons:
                print(f"      匹配: {reasons}")
            
            # 尝试截图
            if is_candidate:
                ts = datetime.now().strftime("%H%M%S_%f")[:10]
                screenshot_file = f"popup_{ts}_{hwnd}.png"
                shot_path = take_screenshot(hwnd, screenshot_file)
                if shot_path:
                    full_info['screenshot'] = screenshot_file
                    print(f"      📸 已截图: {screenshot_file}")


# 保持回调引用(防止GC)
_callback_ref = WinEventProcType(win_event_callback)


# ==================== 并行轮询线程(对比用) ====================

def polling_thread_func():
    """传统轮询方式(与Hook对比)"""
    global monitor_active
    
    # 等待baseline建立
    time.sleep(1)
    
    poll_baseline = set()
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_cb(hwnd, lp):
        if is_window_visible(hwnd):
            poll_baseline.add(hwnd)
        return True
    
    windll.user32.EnumWindows(enum_cb, 0)
    
    poll_detections = []
    
    while monitor_active:
        current = set()
        
        @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def enum_cb2(hwnd, lp):
            if is_window_visible(hwnd):
                current.add(hwnd)
            return True
        
        windll.user32.EnumWindows(enum_cb2, 0)
        
        new_hwnds = current - poll_baseline
        for hwnd in new_hwnds:
            cls = get_window_class(hwnd)
            title = get_window_title(hwnd)
            elapsed_ms = int((time.time() - start_time) * 1000) if start_time else 0
            
            poll_detections.append({
                'hwnd': hwnd,
                'class': cls,
                'title': title[:80],
                'elapsed_ms': elapsed_ms,
            })
        
        poll_baseline.update(current)
        time.sleep(0.05)  # 50ms轮询
    
    # 保存轮询结果供对比
    with log_lock:
        for entry in poll_detections:
            entry['method'] = 'polling'
        events_log.extend(poll_detections)


# ==================== 主函数 ====================

def setup_hooks():
    """设置WinEvent Hook"""
    hooks = []
    
    # 监听多种事件
    events_to_hook = [
        (EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW),
        (EVENT_OBJECT_CREATE, EVENT_OBJECT_CREATE),
        (EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND),
    ]
    
    for event_min, event_max in events_to_hook:
        hook = windll.user32.SetWinEventHook(
            event_min,          # eventMin
            event_max,          # eventMax
            0,                  # hmodWinEventProc (0 = out-of-context)
            _callback_ref,      # pfnWinEventProc
            0,                  # idProcess (0 = all)
            0,                  # idThread (0 = all)
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        
        if hook:
            hooks.append(hook)
        else:
            print(f"  ⚠️ 设置Hook失败: event=0x{event_min:04X}")
    
    return hooks


def record_baseline():
    """记录基准窗口"""
    global baseline_hwnds
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_cb(hwnd, lp):
        if is_window_visible(hwnd):
            baseline_hwnds.add(hwnd)
            seen_hwnds.add(hwnd)
        return True
    
    windll.user32.EnumWindows(enum_cb, 0)
    return len(baseline_hwnds)


def message_pump(timeout_seconds):
    """消息泵 - 必须运行才能接收WinEvent回调"""
    global monitor_active
    
    MSG = ctypes.wintypes.MSG()
    end_time = time.time() + timeout_seconds
    
    while monitor_active and time.time() < end_time:
        # PeekMessage 非阻塞
        result = windll.user32.PeekMessageW(
            byref(MSG), 0, 0, 0, 1  # PM_REMOVE
        )
        if result:
            windll.user32.TranslateMessage(byref(MSG))
            windll.user32.DispatchMessageW(byref(MSG))
        else:
            time.sleep(0.01)  # 避免CPU空转


def main():
    global start_time, monitor_active
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  成交弹窗探测 - WinEvent Hook 版                                    ║
║                                                                      ║
║  原理: 事件驱动, 窗口出现瞬间触发回调, 不可能漏掉                      ║
║                                                                      ║
║  使用方法:                                                           ║
║  1. 按Enter开始监控                                                  ║
║  2. 去华泰xiadan执行一笔真实交易(确保能成交)                          ║
║  3. 脚本会捕获所有新出现的窗口                                        ║
║  4. 120秒后自动结束, 或按Ctrl+C手动结束                              ║
║                                                                      ║
║  产出: popup_hook_result.json                                        ║
║  截图: popup_screenshots/ 目录                                       ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查截图依赖
    try:
        from PIL import ImageGrab
        print("  ✅ PIL/Pillow 已安装 (支持截图)")
    except ImportError:
        print("  ⚠️ PIL/Pillow 未安装 (无法截图, 不影响检测)")
        print("     pip install Pillow")
    
    print()
    input("  准备好后按Enter开始监控...")
    
    # 1. 记录基准
    print("\n  📋 记录基准窗口...")
    baseline_count = record_baseline()
    print(f"  基准窗口数: {baseline_count}")
    
    # 2. 设置Hook
    print("\n  🔗 设置WinEvent Hook...")
    hooks = setup_hooks()
    print(f"  已设置 {len(hooks)} 个Hook")
    
    if not hooks:
        print("  ❌ 无法设置Hook, 退出")
        return
    
    # 3. 启动轮询线程(对比用)
    print("  🔄 启动并行轮询线程(50ms, 用于对比)")
    poll_thread = threading.Thread(target=polling_thread_func, daemon=True)
    poll_thread.start()
    
    # 4. 开始监控
    start_time = time.time()
    print(f"\n  🟢 开始监控! (持续{MONITOR_SECONDS}秒)")
    print(f"  现在去华泰xiadan执行买入操作...")
    print(f"  所有新出现的窗口都会被记录\n")
    print(f"  {'─'*60}")
    
    try:
        # 运行消息泵(接收WinEvent回调)
        message_pump(MONITOR_SECONDS)
    except KeyboardInterrupt:
        print("\n\n  ⏹ 用户中断")
    finally:
        monitor_active = False
    
    # 5. 清理Hook
    print(f"\n  {'─'*60}")
    print(f"\n  🔴 监控结束")
    for hook in hooks:
        windll.user32.UnhookWinEvent(hook)
    
    # 6. 输出结果
    elapsed_total = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"  📊 监控结果")
    print(f"{'='*60}")
    print(f"\n  监控时长: {elapsed_total:.1f}秒")
    print(f"  事件总数: {len(events_log)}")
    print(f"  新窗口数: {len(new_windows_log)}")
    
    # 统计候选弹窗
    candidates = [w for w in new_windows_log if w.get('is_candidate')]
    print(f"  候选弹窗: {len(candidates)} 个")
    
    if candidates:
        print(f"\n  🔴 候选弹窗详情:")
        for i, c in enumerate(candidates, 1):
            print(f"\n  [{i}] {c['class_name']}")
            print(f"      标题: '{c['title']}'")
            rect = c.get('rect')
            if rect:
                print(f"      位置: ({rect['left']},{rect['top']}) 大小: {rect['width']}x{rect['height']}")
            print(f"      进程: {c['process_name']} (PID={c['pid']})")
            print(f"      时间: +{c['elapsed_ms']}ms")
            print(f"      匹配原因: {c['candidate_reasons']}")
            if c.get('child_texts'):
                print(f"      内容: {[t['text'][:40] for t in c['child_texts']]}")
            if c.get('screenshot'):
                print(f"      截图: {c['screenshot']}")
    else:
        print(f"\n  ⚠️ 未发现候选弹窗!")
        print(f"  可能原因:")
        print(f"    1. 交易未成交")
        print(f"    2. 弹窗类型超出预期(查看下方所有新窗口)")
        print(f"    3. 弹窗在脚本启动前就出现了")
    
    # 显示所有新窗口
    if new_windows_log:
        print(f"\n  📋 所有新窗口 ({len(new_windows_log)}个):")
        for i, w in enumerate(new_windows_log, 1):
            marker = "🔴" if w.get('is_candidate') else "⚪"
            rect = w.get('rect', {})
            size_str = f"{rect.get('width','?')}x{rect.get('height','?')}" if rect else "?"
            print(f"    {marker} [{w['elapsed_ms']}ms] {w['class_name'][:40]} "
                  f"\"{w['title'][:30]}\" {size_str} ({w['process_name']})")
    
    # 7. 保存结果
    result = {
        'meta': {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': round(elapsed_total, 1),
            'baseline_count': baseline_count,
            'total_events': len(events_log),
            'new_windows_count': len(new_windows_log),
            'candidates_count': len(candidates),
        },
        'candidates': candidates,
        'all_new_windows': new_windows_log,
        'events_sample': events_log[:200],  # 只保存前200条事件
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  💾 结果已保存: {OUTPUT_FILE}")
    
    # 8. 给出建议
    print(f"\n{'='*60}")
    print(f"  💡 下一步")
    print(f"{'='*60}")
    
    if candidates:
        print(f"\n  有 {len(candidates)} 个候选弹窗, 请确认:")
        print(f"  1. 查看截图确认是否为成交弹窗")
        print(f"  2. 记录确认的窗口特征(类名/大小/位置)")
        print(f"  3. 将特征更新到 auto_trader.py 的检测逻辑中")
    else:
        print(f"\n  没有候选弹窗, 请检查:")
        print(f"  1. 交易是否真的成交了?")
        print(f"  2. 查看 '所有新窗口' 列表, 成交弹窗可能不符合预设条件")
        print(f"  3. 把 popup_hook_result.json 发给我分析")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  ❌ 脚本异常: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
