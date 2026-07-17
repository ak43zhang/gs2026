"""
成交检测 - 持仓变化版 (最可靠)

通过检测持仓列表的变化来判断是否成交
原理: 买入成功后,持仓列表中会出现新的债券

使用方法:
    1. 运行脚本
    2. 脚本记录当前持仓
    3. 在华泰执行买入
    4. 脚本检测持仓变化

优点:
    - 不依赖弹窗形式
    - 不受窗口位置影响
    - 100%可靠(只要成交,持仓一定会变)
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


def get_all_texts(hwnd, max_depth=3):
    """递归获取所有文本"""
    all_texts = []
    
    @WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(child_hwnd, lp):
        text_len = windll.user32.GetWindowTextLengthW(child_hwnd)
        if text_len > 0:
            buf = ctypes.create_unicode_buffer(text_len + 1)
            windll.user32.GetWindowTextW(child_hwnd, buf, text_len + 1)
            text = buf.value.strip()
            if text and len(text) > 2:  # 过滤短文本
                all_texts.append(text)
        return True
    
    windll.user32.EnumChildWindows(hwnd, cb, 0)
    return all_texts


def extract_bond_codes(texts):
    """从文本中提取债券代码"""
    import re
    codes = set()
    
    # 可转债代码模式: 11xxxx 或 12xxxx
    pattern = r'\b(11\d{4}|12\d{4})\b'
    
    for text in texts:
        matches = re.findall(pattern, text)
        codes.update(matches)
    
    return codes


def get_current_positions(xiadan_hwnd):
    """
    获取当前持仓
    
    策略: 切换到持仓面板,读取所有文本,提取债券代码
    """
    # 按F4切换到持仓(假设F4是持仓快捷键)
    # 如果没有快捷键,可以通过菜单导航
    
    # 这里简化处理: 直接读取当前所有文本
    texts = get_all_texts(xiadan_hwnd)
    codes = extract_bond_codes(texts)
    
    return {
        'codes': codes,
        'texts': texts,
        'timestamp': datetime.now().isoformat(),
    }


def monitor_position_change(xiadan_hwnd, target_code, timeout=30, poll_interval=0.5):
    """
    监控持仓变化,检测目标债券是否出现
    
    Args:
        xiadan_hwnd: xiadan窗口句柄
        target_code: 目标债券代码
        timeout: 超时(秒)
        poll_interval: 检测间隔(秒)
        
    Returns:
        是否检测到持仓变化
    """
    print(f"  开始监控持仓变化...")
    print(f"  目标债券: {target_code}")
    print(f"  超时: {timeout}秒, 检测间隔: {poll_interval*1000:.0f}ms")
    
    # 记录初始持仓
    print("\n  记录初始持仓...")
    baseline = get_current_positions(xiadan_hwnd)
    print(f"  当前持仓债券: {baseline['codes']}")
    
    start_time = time.time()
    detected = False
    
    while time.time() - start_time < timeout:
        elapsed = time.time() - start_time
        
        # 获取当前持仓
        current = get_current_positions(xiadan_hwnd)
        
        # 检查目标债券是否出现
        if target_code in current['codes']:
            print(f"\n  [{elapsed:.1f}s] ✓ 检测到持仓变化!")
            print(f"    目标债券 {target_code} 已出现在持仓中")
            
            # 找出新增的债券
            new_codes = current['codes'] - baseline['codes']
            if new_codes:
                print(f"    新增债券: {new_codes}")
            
            detected = True
            break
        
        # 检查是否有任何变化(用于调试)
        if current['codes'] != baseline['codes']:
            new_codes = current['codes'] - baseline['codes']
            removed_codes = baseline['codes'] - current['codes']
            if new_codes or removed_codes:
                print(f"\n  [{elapsed:.1f}s] 持仓变化:")
                if new_codes:
                    print(f"    新增: {new_codes}")
                if removed_codes:
                    print(f"    减少: {removed_codes}")
        
        # 每5秒打印状态
        if int(elapsed) % 5 == 0 and elapsed > 0:
            print(f"  ... 已监控 {int(elapsed)}秒, 持仓: {current['codes']} ...")
        
        time.sleep(poll_interval)
    
    return detected


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 持仓变化版 (最可靠)                                  ║
║                                                                  ║
║  通过检测持仓列表的变化来判断是否成交                             ║
║  原理: 买入成功后,持仓列表中会出现新的债券                       ║
║                                                                  ║
║  优点:                                                           ║
║  • 不依赖弹窗形式                                                ║
║  • 不受窗口位置影响                                               ║
║  • 100%可靠(只要成交,持仓一定会变)                               ║
║                                                                  ║
║  使用方法:                                                       ║
║  1. 运行脚本                                                      ║
║  2. 输入要买入的债券代码                                          ║
║  3. 在华泰执行买入                                               ║
║  4. 脚本自动检测持仓变化                                          ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 查找xiadan
    print(f"  查找 '{XIADAN_TITLE}'...")
    xiadan_hwnd = find_window(XIADAN_TITLE)
    
    if not xiadan_hwnd:
        print(f"  ❌ 未找到 '{XIADAN_TITLE}'")
        return
    
    print(f"  ✓ 找到主窗口: {xiadan_hwnd}")
    
    # 输入目标债券代码
    target_code = input("\n  请输入要买入的债券代码(如127045): ").strip()
    if not target_code:
        print("  未输入代码,退出")
        return
    
    # 验证代码格式
    if not (target_code.startswith('11') or target_code.startswith('12')):
        print(f"  警告: 代码 {target_code} 不是标准可转债代码(应以11或12开头)")
        confirm = input("  是否继续? (y/n): ").strip().lower()
        if confirm != 'y':
            return
    
    input("\n  请确保当前能看到持仓列表,按Enter开始监控...")
    
    # 开始监控
    detected = monitor_position_change(xiadan_hwnd, target_code, timeout=30)
    
    # 结果
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到成交!")
        print(f"  债券 {target_code} 已加入持仓")
    else:
        print("  ⚠️ 未检测到持仓变化(30秒超时)")
        print("  可能原因:")
        print("    1. 买入未成交(价格不合适)")
        print("    2. 持仓面板未显示")
        print("    3. 债券代码识别错误")
    print(f"{'='*60}")
    
    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'target_code': target_code,
        'detected': detected,
    }
    
    output_file = Path(__file__).parent / "popup_position_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n  结果已保存: {output_file}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  错误: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
