"""
成交检测 - 文本提取版

问题: window.texts() 返回空列表
解决: 使用多种方法尝试提取文本

方法1: window.texts() - UIA方法
方法2: 遍历所有子控件获取文本
方法3: 使用Win32 API发送WM_GETTEXT
方法4: OCR截图识别
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref
from datetime import datetime
from pathlib import Path
import json
import re

# 监控区域
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
    windows = []
    from ctypes import WINFUNCTYPE
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, lp):
        if is_window_visible(hwnd) and is_window_in_region(hwnd, region):
            windows.append(hwnd)
        return True
    windll.user32.EnumWindows(cb, 0)
    return windows


def get_texts_method1_uia(hwnd):
    """方法1: UIA texts()"""
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        window = desktop.window(handle=hwnd)
        return window.texts()
    except Exception as e:
        return [f"UIA Error: {e}"]


def get_texts_method2_children(hwnd):
    """方法2: 遍历子控件"""
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        window = desktop.window(handle=hwnd)
        
        all_texts = []
        
        # 递归获取所有子控件文本
        def get_children_texts(ctrl, depth=0):
            if depth > 3:  # 限制深度
                return
            try:
                text = ctrl.window_text()
                if text and text.strip():
                    all_texts.append(text.strip())
                
                for child in ctrl.children():
                    get_children_texts(child, depth + 1)
            except:
                pass
        
        get_children_texts(window)
        return all_texts
    except Exception as e:
        return [f"Children Error: {e}"]


def get_texts_method3_win32(hwnd):
    """方法3: Win32 WM_GETTEXT"""
    try:
        # 获取窗口文本
        length = windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return [buf.value]
        return []
    except Exception as e:
        return [f"Win32 Error: {e}"]


def get_texts_method4_enum_child(hwnd):
    """方法4: 枚举子窗口获取文本"""
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


def get_all_texts_methods(hwnd):
    """使用所有方法获取文本"""
    results = {
        'method1_uia': get_texts_method1_uia(hwnd),
        'method2_children': get_texts_method2_children(hwnd),
        'method3_win32': get_texts_method3_win32(hwnd),
        'method4_enum_child': get_texts_method4_enum_child(hwnd),
    }
    return results


def capture_and_ocr(hwnd):
    """方法5: 截图OCR"""
    try:
        from PIL import Image
        import win32gui
        import win32ui
        import win32con
        
        # 获取窗口位置
        left, top, right, bottom = get_window_rect(hwnd)
        width = right - left
        height = bottom - top
        
        # 截图
        hwndDC = win32gui.GetWindowDC(hwnd)
        img_dc = win32ui.CreateDCFromHandle(hwndDC)
        mem_dc = img_dc.CreateCompatibleDC()
        
        screenshot = win32ui.CreateBitmap()
        screenshot.CreateCompatibleBitmap(img_dc, width, height)
        mem_dc.SelectObject(screenshot)
        
        mem_dc.BitBlt((0, 0), (width, height), img_dc, (0, 0), win32con.SRCCOPY)
        
        bmpinfo = screenshot.GetInfo()
        bmpstr = screenshot.GetBitmapBits(True)
        im = Image.frombuffer(
            'RGB',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRX', 0, 1)
        
        win32gui.DeleteObject(screenshot.GetHandle())
        mem_dc.DeleteDC()
        img_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        
        # OCR
        try:
            import pytesseract
            text = pytesseract.image_to_string(im, lang='chi_sim+eng')
            return [text]
        except:
            return ["OCR not available"]
            
    except Exception as e:
        return [f"OCR Error: {e}"]


def monitor_with_text_extraction(target_code=None, timeout=30):
    """带多种文本提取方法的监控"""
    print("=" * 60)
    print("成交检测 - 文本提取版")
    print("=" * 60)
    
    print(f"\n  监控区域: {MONITOR_REGION}")
    print(f"  目标代码: {target_code or '任意'}")
    print(f"  超时: {timeout}秒")
    print()
    
    # 记录基准
    print("  记录基准状态...")
    hwnds = enum_windows_in_region(MONITOR_REGION)
    baseline = set()
    for hwnd in hwnds:
        cls = get_window_class(hwnd)
        if cls.startswith("Afx:"):
            baseline.add(hwnd)
    print(f"  基准Afx窗口: {len(baseline)}")
    
    print("\n  开始监控... (按Ctrl+C停止)\n")
    
    handled = set()
    start_time = time.time()
    
    try:
        while time.time() - start_time < timeout:
            hwnds = enum_windows_in_region(MONITOR_REGION)
            current = set()
            for hwnd in hwnds:
                cls = get_window_class(hwnd)
                if cls.startswith("Afx:"):
                    current.add(hwnd)
            
            # 新窗口
            new_hwnds = current - baseline - handled
            
            for hwnd in new_hwnds:
                elapsed = time.time() - start_time
                cls = get_window_class(hwnd)
                
                print(f"\n{'='*60}")
                print(f"  [{elapsed:.1f}s] ★ 发现新窗口!")
                print(f"{'='*60}")
                print(f"  句柄: {hwnd}")
                print(f"  类名: {cls}")
                
                # 尝试所有方法获取文本
                print(f"\n  --- 尝试所有文本提取方法 ---")
                
                all_results = get_all_texts_methods(hwnd)
                all_texts = []
                
                for method_name, texts in all_results.items():
                    print(f"\n  {method_name}:")
                    print(f"    结果数: {len(texts)}")
                    for i, text in enumerate(texts[:5]):  # 只显示前5个
                        print(f"      [{i}] \"{text[:80]}\"")
                    all_texts.extend(texts)
                
                # 方法5: OCR
                print(f"\n  method5_ocr:")
                ocr_texts = capture_and_ocr(hwnd)
                for text in ocr_texts[:1]:
                    print(f"    \"{text[:200]}\"")
                all_texts.extend(ocr_texts)
                
                # 合并所有文本
                full_content = "\n".join(all_texts)
                
                # 分析
                print(f"\n  --- 内容分析 ---")
                print(f"  总文本长度: {len(full_content)}")
                
                # 检查关键词
                keywords = ["买入", "卖出", "成交", "委托", "价格", "数量"]
                found = [kw for kw in keywords if kw in full_content]
                print(f"  找到的关键词: {found}")
                
                # 查找代码
                codes = re.findall(r'\b(\d{6})\b', full_content)
                print(f"  找到的代码: {codes}")
                
                # 匹配检查
                if codes:
                    for code in codes:
                        if not target_code or code == target_code:
                            print(f"\n  ★★★ 成交确认! 代码: {code} ★★★")
                            return True, {
                                'hwnd': hwnd,
                                'code': code,
                                'content': full_content,
                            }
                
                handled.add(hwnd)
            
            baseline.update(current)
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n  用户中断")
    
    print(f"\n  监听超时")
    return False, None


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 文本提取版 (5种方法)                                 ║
║                                                                  ║
║  尝试所有可能的文本提取方法:                                     ║
║  1. UIA texts()                                                  ║
║  2. 遍历子控件                                                   ║
║  3. Win32 WM_GETTEXT                                             ║
║  4. 枚举子窗口                                                   ║
║  5. 截图OCR                                                      ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    target_code = input("\n  请输入要检测的债券代码(直接回车=检测任意): ").strip()
    
    input("\n  按Enter开始,然后去华泰执行买入...")
    
    detected, info = monitor_with_text_extraction(
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
