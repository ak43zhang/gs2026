"""
成交检测 - 像素变化版 (最快响应)

原理: 监控屏幕右下角特定区域的像素变化
当弹窗出现时,该区域像素会发生明显变化

优点:
- 最快响应 (50ms级别)
- 不依赖窗口句柄
- 不受窗口遍历延迟影响

使用方法:
    1. 运行脚本
    2. 脚本记录基准截图
    3. 在华泰执行买入
    4. 脚本检测像素变化,判断弹窗出现
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref
from datetime import datetime
from pathlib import Path
import json

# 监控区域 - 屏幕右下角 (根据实测弹窗位置)
MONITOR_RECT = {
    'left': 1400,
    'top': 800,
    'width': 520,   # 1920-1400
    'height': 280, # 1080-800
}

# 变化阈值 - 超过此值认为有变化
CHANGE_THRESHOLD = 1000


def capture_screen_region(left, top, width, height):
    """截取屏幕区域"""
    try:
        from PIL import Image
        import win32gui
        import win32ui
        import win32con
        
        # 创建DC
        hdesktop = win32gui.GetDesktopWindow()
        desktop_dc = win32gui.GetWindowDC(hdesktop)
        img_dc = win32ui.CreateDCFromHandle(desktop_dc)
        mem_dc = img_dc.CreateCompatibleDC()
        
        # 创建位图
        screenshot = win32ui.CreateBitmap()
        screenshot.CreateCompatibleBitmap(img_dc, width, height)
        mem_dc.SelectObject(screenshot)
        
        # 复制屏幕
        mem_dc.BitBlt((0, 0), (width, height), img_dc, (left, top), win32con.SRCCOPY)
        
        # 转换为PIL Image
        bmpinfo = screenshot.GetInfo()
        bmpstr = screenshot.GetBitmapBits(True)
        im = Image.frombuffer(
            'RGB',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRX', 0, 1)
        
        # 清理
        win32gui.DeleteObject(screenshot.GetHandle())
        mem_dc.DeleteDC()
        img_dc.DeleteDC()
        win32gui.ReleaseDC(hdesktop, desktop_dc)
        
        return im
        
    except Exception as e:
        print(f"截图失败: {e}")
        return None


def image_to_pixels(image):
    """将图像转换为像素列表(用于比较)"""
    return list(image.getdata())


def count_diff_pixels(pixels1, pixels2, threshold=30):
    """计算差异像素数量"""
    if len(pixels1) != len(pixels2):
        return float('inf')
    
    diff_count = 0
    for p1, p2 in zip(pixels1, pixels2):
        # 计算RGB差异
        r_diff = abs(p1[0] - p2[0])
        g_diff = abs(p1[1] - p2[1])
        b_diff = abs(p1[2] - p2[2])
        
        # 如果任一通道差异超过阈值,计为变化
        if r_diff > threshold or g_diff > threshold or b_diff > threshold:
            diff_count += 1
    
    return diff_count


def monitor_pixel_change(timeout=30, poll_ms=50, save_images=True):
    """
    监控像素变化
    
    Args:
        timeout: 超时秒数
        poll_ms: 检测间隔毫秒
        save_images: 是否保存截图
        
    Returns:
        是否检测到变化
    """
    print("=" * 60)
    print("成交检测 - 像素变化版 (最快响应)")
    print("=" * 60)
    
    left = MONITOR_RECT['left']
    top = MONITOR_RECT['top']
    width = MONITOR_RECT['width']
    height = MONITOR_RECT['height']
    
    print(f"\n  监控区域: ({left}, {top}) 大小: {width}x{height}")
    print(f"  超时: {timeout}秒")
    print(f"  检测间隔: {poll_ms}ms")
    print(f"  变化阈值: {CHANGE_THRESHOLD}像素")
    print()
    
    # 创建截图目录
    if save_images:
        screenshot_dir = Path(__file__).parent / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        print(f"  截图保存到: {screenshot_dir}")
    
    # 记录基准截图
    print("\n  记录基准截图...")
    baseline_image = capture_screen_region(left, top, width, height)
    
    if not baseline_image:
        print("  ❌ 基准截图失败")
        return False, None
    
    baseline_pixels = image_to_pixels(baseline_image)
    print(f"  ✓ 基准截图: {baseline_image.size}, {len(baseline_pixels)}像素")
    
    # 保存基准
    if save_images:
        baseline_path = screenshot_dir / "baseline.png"
        baseline_image.save(baseline_path)
        print(f"  已保存: {baseline_path}")
    
    print("\n  开始监控像素变化... (按Ctrl+C停止)\n")
    
    start_time = time.time()
    screenshot_count = 0
    
    try:
        while time.time() - start_time < timeout:
            # 截图
            current_image = capture_screen_region(left, top, width, height)
            screenshot_count += 1
            
            if not current_image:
                continue
            
            current_pixels = image_to_pixels(current_image)
            
            # 计算差异
            diff_count = count_diff_pixels(baseline_pixels, current_pixels)
            
            # 检查是否超过阈值
            if diff_count > CHANGE_THRESHOLD:
                elapsed = time.time() - start_time
                print(f"\n  [{elapsed:.2f}s] ★★★ 检测到像素变化! ★★★")
                print(f"    变化像素数: {diff_count}")
                
                # 保存当前截图
                if save_images:
                    timestamp = datetime.now().strftime("%H%M%S_%f")[:-3]
                    current_path = screenshot_dir / f"detected_{timestamp}.png"
                    current_image.save(current_path)
                    print(f"    已保存: {current_path}")
                
                # 尝试OCR识别内容
                try:
                    import pytesseract
                    text = pytesseract.image_to_string(current_image, lang='chi_sim+eng')
                    print(f"    OCR识别: {text[:100]}...")
                    
                    # 检查是否包含买入
                    if "买入" in text:
                        print(f"\n  ✓ 确认是成交弹窗!")
                        
                        # 提取代码
                        import re
                        code_match = re.search(r'\b(\d{6})\b', text)
                        if code_match:
                            print(f"    代码: {code_match.group(1)}")
                        
                        return True, {
                            'diff_pixels': diff_count,
                            'text': text,
                            'timestamp': datetime.now().isoformat(),
                        }
                except:
                    pass
                
                # 即使没有OCR,也返回检测到变化
                return True, {
                    'diff_pixels': diff_count,
                    'timestamp': datetime.now().isoformat(),
                }
            
            # 每3秒打印状态
            elapsed = int(time.time() - start_time)
            if elapsed % 3 == 0 and elapsed > 0 and screenshot_count % 60 == 0:
                print(f"  ... 已监控 {elapsed}秒, 截图{screenshot_count}张, 无变化 ...")
            
            time.sleep(poll_ms / 1000)
    
    except KeyboardInterrupt:
        print("\n  用户中断")
    
    print(f"\n  监听超时 ({timeout}秒)")
    print(f"  共截图 {screenshot_count} 张")
    return False, None


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 像素变化版 (最快响应)                                ║
║                                                                  ║
║  原理: 监控屏幕右下角像素变化,不依赖窗口句柄                    ║
║                                                                  ║
║  优点:                                                           ║
║  • 最快响应 (50ms级别)                                          ║
║  • 不依赖窗口句柄                                                ║
║  • 不受窗口遍历延迟影响                                          ║
║                                                                  ║
║  依赖: pip install pillow pytesseract                           ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查依赖
    try:
        from PIL import Image
        print("✓ PIL 已安装")
    except ImportError:
        print("❌ 未安装 PIL")
        print("   pip install pillow")
        return
    
    try:
        import win32gui
        print("✓ pywin32 已安装")
    except ImportError:
        print("❌ 未安装 pywin32")
        print("   pip install pywin32")
        return
    
    input("\n  按Enter开始记录基准,然后去华泰执行买入...")
    
    # 开始监控
    detected, info = monitor_pixel_change(
        timeout=30,
        poll_ms=50,
        save_images=True
    )
    
    # 结果
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到像素变化!")
        print(f"  信息: {info}")
    else:
        print("  ⚠️ 未检测到变化")
        print("  请检查 screenshots 目录中的截图")
    print(f"{'='*60}")
    
    # 保存
    result = {
        'timestamp': datetime.now().isoformat(),
        'detected': detected,
        'info': info,
        'monitor_rect': MONITOR_RECT,
    }
    
    output_file = Path(__file__).parent / "popup_pixel_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")


if __name__ == '__main__':
    main()
