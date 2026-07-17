"""
成交检测 - 截图OCR版

通过定时截图+OCR识别来判断是否出现成交提示
适用于任何形式的提示(独立窗口/子窗口/内部消息)

使用方法:
    1. 确保安装了依赖: pip install pillow pytesseract
    2. 安装Tesseract-OCR: https://github.com/UB-Mannheim/tesseract/wiki
    3. 运行脚本
    4. 在华泰执行买入
    5. 脚本自动截图识别
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from datetime import datetime
from pathlib import Path
import json

XIADAN_TITLE = "网上股票交易系统5.0"


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


def get_window_rect(hwnd):
    """获取窗口矩形"""
    rect = ctypes.wintypes.RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def capture_window(hwnd, filename=None):
    """截图窗口"""
    try:
        from PIL import Image
        import win32gui
        import win32ui
        import win32con
        
        # 获取窗口DC
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        
        # 获取窗口大小
        left, top, right, bottom = get_window_rect(hwnd)
        width = right - left
        height = bottom - top
        
        # 创建位图
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
        saveDC.SelectObject(saveBitMap)
        
        # 截图
        saveDC.BitBlt((0, 0), (width, height), mfcDC, (0, 0), win32con.SRCCOPY)
        
        # 转换为PIL Image
        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        im = Image.frombuffer(
            'RGB',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRX', 0, 1)
        
        # 清理
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        
        # 保存
        if filename:
            im.save(filename)
        
        return im
        
    except Exception as e:
        print(f"  截图失败: {e}")
        return None


def ocr_image(image, keywords=["成交", "委托", "成功", "买入", "卖出"]):
    """OCR识别图像中的文字"""
    try:
        import pytesseract
        
        # 识别文字
        text = pytesseract.image_to_string(image, lang='chi_sim+eng')
        
        # 检查关键词
        matched = [kw for kw in keywords if kw in text]
        
        return {
            'text': text,
            'matched': matched,
            'has_match': len(matched) > 0,
        }
        
    except Exception as e:
        print(f"  OCR失败: {e}")
        return {'text': '', 'matched': [], 'has_match': False}


def monitor_by_screenshot(xiadan_hwnd, timeout=30, poll_interval=0.5, save_images=True):
    """
    通过截图OCR监控成交
    
    Args:
        xiadan_hwnd: xiadan窗口句柄
        timeout: 超时(秒)
        poll_interval: 截图间隔(秒)
        save_images: 是否保存截图
        
    Returns:
        是否检测到成交
    """
    print(f"  开始截图监控...")
    print(f"  超时: {timeout}秒, 截图间隔: {poll_interval*1000:.0f}ms")
    
    # 创建截图目录
    if save_images:
        screenshot_dir = Path(__file__).parent / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        print(f"  截图保存到: {screenshot_dir}")
    
    start_time = time.time()
    detected = False
    detection_info = None
    screenshot_count = 0
    
    while time.time() - start_time < timeout:
        elapsed = time.time() - start_time
        
        # 截图
        timestamp = datetime.now().strftime("%H%M%S_%f")[:-3]
        if save_images:
            filename = screenshot_dir / f"xiadan_{timestamp}.png"
            image = capture_window(xiadan_hwnd, filename)
        else:
            image = capture_window(xiadan_hwnd)
        
        screenshot_count += 1
        
        if image:
            # OCR识别
            result = ocr_image(image)
            
            if result['has_match']:
                print(f"\n  [{elapsed:.1f}s] ✓ 检测到关键词!")
                print(f"    匹配: {result['matched']}")
                print(f"    文字片段: {result['text'][:100]}...")
                detected = True
                detection_info = result
                break
            else:
                # 每5秒打印一次状态
                if screenshot_count % 10 == 0:
                    print(f"  ... 已截图{screenshot_count}张, 未检测到关键词 ...")
        
        time.sleep(poll_interval)
    
    print(f"\n  共截图 {screenshot_count} 张")
    return detected, detection_info


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 截图OCR版                                            ║
║                                                                  ║
║  通过定时截图+OCR识别来判断是否出现成交提示                       ║
║  适用于任何形式的提示                                           ║
║                                                                  ║
║  前置条件:                                                       ║
║  1. pip install pillow pytesseract                               ║
║  2. 安装Tesseract-OCR引擎                                       ║
║                                                                  ║
║  使用方法:                                                       ║
║  1. 运行脚本                                                      ║
║  2. 在华泰执行买入                                               ║
║  3. 脚本自动截图识别                                              ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查依赖
    try:
        from PIL import Image
        import pytesseract
        print("  ✓ 依赖检查通过 (PIL, pytesseract)")
    except ImportError as e:
        print(f"  ❌ 缺少依赖: {e}")
        print("\n  请安装:")
        print("    pip install pillow pytesseract")
        print("    pip install pywin32")
        print("\n  并安装Tesseract-OCR:")
        print("    https://github.com/UB-Mannheim/tesseract/wiki")
        return
    
    # 查找xiadan
    print(f"\n  查找 '{XIADAN_TITLE}'...")
    xiadan_hwnd = find_window(XIADAN_TITLE)
    
    if not xiadan_hwnd:
        print(f"  ❌ 未找到 '{XIADAN_TITLE}'")
        return
    
    print(f"  ✓ 找到主窗口: {xiadan_hwnd}")
    
    # 测试截图
    print("\n  测试截图...")
    test_image = capture_window(xiadan_hwnd)
    if test_image:
        print(f"  ✓ 截图成功: {test_image.size}")
        
        # 测试OCR
        print("  测试OCR...")
        result = ocr_image(test_image)
        print(f"  ✓ OCR成功, 识别到 {len(result['text'])} 字符")
        if result['text']:
            print(f"    样本: \"{result['text'][:80]}...\"")
    else:
        print("  ❌ 截图失败")
        return
    
    input("\n  请去华泰执行一笔买入,按Enter开始监控...")
    
    # 开始监控
    detected, info = monitor_by_screenshot(xiadan_hwnd, timeout=30, save_images=True)
    
    # 结果
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到成交!")
        print(f"  匹配关键词: {info['matched']}")
        print(f"  识别文字: \"{info['text'][:200]}\"")
    else:
        print("  ⚠️ 未检测到成交(30秒超时)")
        print("  请检查 screenshots 目录中的截图")
    print(f"{'='*60}")
    
    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'detected': detected,
        'info': info,
    }
    
    output_file = Path(__file__).parent / "popup_screenshot_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  错误: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
