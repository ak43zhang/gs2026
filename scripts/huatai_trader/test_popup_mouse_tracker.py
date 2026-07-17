"""
成交弹窗鼠标追踪器

实时显示鼠标下的窗口信息，帮助定位弹窗

使用方法:
    1. 运行脚本
    2. 在华泰执行买入
    3. 弹窗出现后，将鼠标移到弹窗上
    4. 观察脚本输出的窗口信息
    5. 按Ctrl+C停止
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref
import sys


def get_mouse_pos():
    """获取鼠标位置"""
    pt = ctypes.wintypes.POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt.x, pt.y


def get_window_at_mouse():
    """获取鼠标下的窗口句柄"""
    pt = ctypes.wintypes.POINT()
    windll.user32.GetCursorPos(byref(pt))
    hwnd = windll.user32.WindowFromPoint(pt)
    return hwnd


def get_window_text(hwnd):
    """获取窗口标题"""
    length = windll.user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_window_class(hwnd):
    """获取窗口类名"""
    buf = ctypes.create_unicode_buffer(256)
    windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_rect(hwnd):
    """获取窗口位置和大小"""
    rect = ctypes.wintypes.RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def is_window_visible(hwnd):
    """检查窗口是否可见"""
    return bool(windll.user32.IsWindowVisible(hwnd))


def get_parent(hwnd):
    """获取父窗口"""
    return windll.user32.GetParent(hwnd)


def format_window_info(hwnd):
    """格式化窗口信息"""
    if not hwnd:
        return "无窗口"
    
    title = get_window_text(hwnd)[:40]
    cls = get_window_class(hwnd)
    left, top, right, bottom = get_window_rect(hwnd)
    width = right - left
    height = bottom - top
    visible = "可见" if is_window_visible(hwnd) else "隐藏"
    
    # 获取父窗口
    parent = get_parent(hwnd)
    parent_info = ""
    if parent:
        parent_title = get_window_text(parent)[:20]
        parent_info = f" 父={parent_title}"
    
    return f"句柄={hwnd:8d} [{cls:20s}] \"{title}\" 位置=({left:4d},{top:4d}) 大小={width}x{height} {visible}{parent_info}"


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交弹窗鼠标追踪器                                              ║
║                                                                  ║
║  实时显示鼠标下的窗口信息                                         ║
║                                                                  ║
║  使用方法:                                                       ║
║  1. 运行脚本                                                      ║
║  2. 在华泰执行买入                                               ║
║  3. 弹窗出现后，将鼠标移到弹窗上                                  ║
║  4. 观察输出的窗口标题和类名                                     ║
║  5. 按Ctrl+C停止                                                 ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    print("\n  开始追踪... (按Ctrl+C停止)\n")
    
    last_info = ""
    
    try:
        while True:
            # 获取鼠标下的窗口
            hwnd = get_window_at_mouse()
            
            # 格式化信息
            info = format_window_info(hwnd)
            
            # 只在变化时打印
            if info != last_info:
                print(f"  {info}")
                last_info = info
            
            # 如果标题包含"成交"，高亮显示
            title = get_window_text(hwnd)
            if "成交" in title or "回报" in title:
                print(f"\n  ★★★ 检测到可能的目标窗口: \"{title}\" ★★★")
                print(f"      句柄: {hwnd}")
                print(f"      类名: {get_window_class(hwnd)}")
                print(f"      按Ctrl+C停止并记录这些信息\n")
            
            time.sleep(0.2)
            
    except KeyboardInterrupt:
        print("\n\n  已停止")
        
        # 最后显示一次当前窗口
        hwnd = get_window_at_mouse()
        print("\n  最后鼠标位置下的窗口:")
        print(f"    {format_window_info(hwnd)}")
        
        # 提示
        print("\n  请记录以下信息用于配置:")
        print(f"    窗口标题: \"{get_window_text(hwnd)}\"")
        print(f"    窗口类名: \"{get_window_class(hwnd)}\"")
        print(f"    窗口句柄: {hwnd}")


if __name__ == '__main__':
    main()
