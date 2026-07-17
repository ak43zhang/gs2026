"""
成交检测 - 已知句柄版

既然已知弹窗句柄是 1445886，直接读取这个句柄的文本
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref
from datetime import datetime
from pathlib import Path
import json
import re

# 已知的弹窗句柄
KNOWN_POPUP_HWND = 1445886


def get_window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def is_window_visible(hwnd):
    return bool(windll.user32.IsWindowVisible(hwnd))


def read_window_text(hwnd):
    """读取窗口文本"""
    length = windll.user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    return ""


def get_all_child_texts(hwnd):
    """获取所有子窗口文本"""
    texts = []
    from ctypes import WINFUNCTYPE
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(child_hwnd, lp):
        length = windll.user32.GetWindowTextLengthW(child_hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            windll.user32.GetWindowTextW(child_hwnd, buf, length + 1)
            text = buf.value.strip()
            if text:
                texts.append(text)
        return True
    
    windll.user32.EnumChildWindows(hwnd, cb, 0)
    return texts


def get_texts_with_uia(hwnd):
    """使用UIA获取文本"""
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        window = desktop.window(handle=hwnd)
        
        # 方法1: texts()
        texts1 = window.texts()
        
        # 方法2: 递归子控件
        all_texts = []
        def get_recursive(ctrl, depth=0):
            if depth > 3:
                return
            try:
                text = ctrl.window_text()
                if text and text.strip():
                    all_texts.append(text.strip())
                for child in ctrl.children():
                    get_recursive(child, depth + 1)
            except:
                pass
        
        get_recursive(window)
        
        return {
            'texts_method': texts1,
            'recursive_method': all_texts,
        }
    except Exception as e:
        return {'error': str(e)}


def monitor_known_hwnd(target_code=None, timeout=30):
    """监控已知句柄"""
    print("=" * 60)
    print("成交检测 - 已知句柄版")
    print("=" * 60)
    print(f"\n  目标句柄: {KNOWN_POPUP_HWND}")
    print(f"  目标代码: {target_code or '任意'}")
    print(f"  超时: {timeout}秒")
    print()
    
    start_time = time.time()
    
    print("  开始监控... (按Ctrl+C停止)\n")
    
    try:
        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            
            # 检查窗口是否可见
            if is_window_visible(KNOWN_POPUP_HWND):
                print(f"\n  [{elapsed:.1f}s] ✓ 窗口可见!")
                
                # 获取位置
                rect = get_window_rect(KNOWN_POPUP_HWND)
                print(f"  位置: {rect}")
                
                # 尝试各种方法获取文本
                print(f"\n  --- Win32 方法 ---")
                
                # 方法1: 窗口标题
                title = read_window_text(KNOWN_POPUP_HWND)
                print(f"  窗口标题: '{title}'")
                
                # 方法2: 子窗口文本
                child_texts = get_all_child_texts(KNOWN_POPUP_HWND)
                print(f"  子窗口文本数: {len(child_texts)}")
                for i, text in enumerate(child_texts):
                    print(f"    [{i}] \"{text}\"")
                
                # 方法3: UIA
                print(f"\n  --- UIA 方法 ---")
                uia_results = get_texts_with_uia(KNOWN_POPUP_HWND)
                
                if 'error' in uia_results:
                    print(f"  UIA错误: {uia_results['error']}")
                else:
                    print(f"  texts() 方法:")
                    for i, text in enumerate(uia_results.get('texts_method', [])):
                        print(f"    [{i}] \"{text}\"")
                    
                    print(f"  递归方法:")
                    for i, text in enumerate(uia_results.get('recursive_method', [])[:10]):
                        print(f"    [{i}] \"{text}\"")
                
                # 合并所有文本进行分析
                all_texts = [title] + child_texts
                if 'texts_method' in uia_results:
                    all_texts.extend(uia_results['texts_method'])
                if 'recursive_method' in uia_results:
                    all_texts.extend(uia_results['recursive_method'])
                
                full_content = "\n".join(all_texts)
                
                # 分析
                print(f"\n  --- 内容分析 ---")
                print(f"  总文本长度: {len(full_content)}")
                
                # 检查关键词
                keywords = ["买入", "卖出", "成交", "委托", "价格", "数量", "证券"]
                found = [kw for kw in keywords if kw in full_content]
                print(f"  关键词: {found}")
                
                # 查找代码
                codes = re.findall(r'\b(\d{6})\b', full_content)
                print(f"  代码: {codes}")
                
                # 匹配
                if codes:
                    for code in codes:
                        if not target_code or code == target_code:
                            print(f"\n  ★★★ 成交确认! 代码: {code} ★★★")
                            
                            # 尝试关闭
                            try:
                                from pywinauto import Desktop
                                desktop = Desktop(backend="uia")
                                window = desktop.window(handle=KNOWN_POPUP_HWND)
                                ok_btn = window.child_window(title="确定", control_type="Button")
                                if ok_btn.exists(timeout=0.5):
                                    ok_btn.click()
                                    print("  已关闭弹窗")
                            except:
                                pass
                            
                            return True, {
                                'hwnd': KNOWN_POPUP_HWND,
                                'code': code,
                                'content': full_content,
                            }
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n  用户中断")
    
    print(f"\n  监听超时")
    return False, None


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 已知句柄版                                           ║
║                                                                  ║
║  直接读取已知句柄 1445886 的文本内容                             ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    target_code = input("\n  请输入要检测的债券代码(直接回车=检测任意): ").strip()
    
    print("\n  请在华泰执行买入，脚本会自动检测...")
    print("  (不需要按Enter，直接开始监控)\n")
    
    detected, info = monitor_known_hwnd(
        target_code=target_code or None,
        timeout=30
    )
    
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到成交!")
        print(f"  信息: {info}")
    else:
        print("  ⚠️ 未检测到成交")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
