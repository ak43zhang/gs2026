"""
成交检测 - 按类名和大小匹配 (根据实测数据优化)

根据用户提供的弹窗信息:
- 句柄: 1445886
- 类名: Afx:004D0000:0:00010003:00100075:00000000
- 标题: "" (空)
- 大小: 365x167
- 位置: 屏幕右下角

检测策略:
1. 类名以 "Afx:" 开头
2. 窗口大小在 300-400 x 100-200 范围内
3. 窗口可见
4. 内容包含"买入"和6位代码
"""

import time
import re
from datetime import datetime
from pathlib import Path
import json


def monitor_fill_popup(target_code=None, timeout=30, auto_close=False):
    """
    监听成交弹窗 - 按类名和大小匹配
    
    Args:
        target_code: 目标债券代码
        timeout: 超时(秒)
        auto_close: 是否自动关闭
        
    Returns:
        是否检测到成交
    """
    print("=" * 60)
    print("开始监听成交弹窗 (按类名和大小匹配)...")
    print("=" * 60)
    
    try:
        from pywinauto import Desktop
    except ImportError:
        print("❌ 未安装 pywinauto")
        print("   pip install pywinauto")
        return False, None
    
    print(f"\n  监听参数:")
    print(f"    目标代码: {target_code or '任意'}")
    print(f"    超时: {timeout}秒")
    print(f"    自动关闭: {auto_close}")
    print(f"\n  匹配规则:")
    print(f"    类名: Afx:*")
    print(f"    大小: 300-400 x 100-200")
    print(f"    内容: 包含'买入'和6位代码")
    print()
    
    desktop = Desktop(backend="uia")
    handled_hwnd = set()
    start_time = time.time()
    detected = False
    detection_info = None
    
    while time.time() - start_time < timeout:
        try:
            # 遍历所有窗口
            for window in desktop.windows():
                try:
                    # 检查类名
                    class_name = window.element_info.class_name
                    if not class_name or not class_name.startswith("Afx:"):
                        continue
                    
                    # 检查窗口大小
                    rect = window.rectangle()
                    width = rect.width()
                    height = rect.height()
                    if not (300 < width < 400 and 100 < height < 200):
                        continue
                    
                    hwnd = window.handle
                    if hwnd in handled_hwnd:
                        continue
                    
                    # 检查可见性
                    if not window.is_visible():
                        continue
                    
                    # 获取文本内容
                    all_texts = window.texts()
                    full_content = "\n".join(all_texts)
                    
                    # 检查是否包含买入
                    if "买入" not in full_content:
                        continue
                    
                    print(f"\n  ✓ 发现候选弹窗!")
                    print(f"    类名: {class_name}")
                    print(f"    大小: {width}x{height}")
                    print(f"    句柄: {hwnd}")
                    print(f"    内容: {full_content[:100]}...")
                    
                    # 解析代码
                    code_match = re.search(r'\b(\d{6})\b', full_content)
                    if code_match:
                        detected_code = code_match.group(1)
                        
                        # 验证目标代码
                        if target_code and detected_code != target_code:
                            print(f"    代码不匹配: {detected_code} != {target_code}")
                            continue
                        
                        print(f"\n  ★★★ 成交确认! ★★★")
                        print(f"    代码: {detected_code}")
                        
                        # 提取更多信息
                        price_match = re.search(r'价格[:：]\s*([\d.]+)', full_content)
                        qty_match = re.search(r'数量[:：]\s*(\d+)', full_content)
                        
                        if price_match:
                            print(f"    成交价: {price_match.group(1)}")
                        if qty_match:
                            print(f"    股数: {qty_match.group(1)}")
                        
                        handled_hwnd.add(hwnd)
                        detected = True
                        detection_info = {
                            'class_name': class_name,
                            'hwnd': hwnd,
                            'size': f"{width}x{height}",
                            'code': detected_code,
                            'content': full_content,
                            'timestamp': datetime.now().isoformat(),
                        }
                        
                        # 自动关闭
                        if auto_close:
                            try:
                                ok_btn = window.child_window(title="确定", control_type="Button")
                                if ok_btn.exists(timeout=0.5):
                                    ok_btn.click()
                                    print("    已自动关闭弹窗")
                            except Exception as e:
                                print(f"    关闭弹窗失败: {e}")
                        
                        return detected, detection_info
                    
                except Exception:
                    continue
        
        except Exception as e:
            print(f"  检测异常: {e}")
        
        # 每5秒打印状态
        elapsed = int(time.time() - start_time)
        if elapsed % 5 == 0 and elapsed > 0:
            print(f"  ... 已监听 {elapsed}秒 ...")
        
        time.sleep(0.3)
    
    print(f"\n  监听超时 ({timeout}秒)")
    return False, None


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - 按类名和大小匹配 (根据实测数据优化)                  ║
║                                                                  ║
║  根据用户提供的弹窗信息优化:                                     ║
║  • 类名: Afx:004D0000:0:00010003:00100075:00000000             ║
║  • 标题: "" (空)                                                ║
║  • 大小: 365x167                                                ║
║  • 位置: 屏幕右下角                                            ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 输入目标代码
    target_code = input("\n  请输入要检测的债券代码(直接回车=检测任意): ").strip()
    
    # 是否自动关闭
    auto_close = input("  是否自动关闭弹窗? (y/n): ").strip().lower() == 'y'
    
    input("\n  请去华泰执行买入，按Enter开始监听...")
    
    # 开始监听
    detected, info = monitor_fill_popup(
        target_code=target_code or None,
        timeout=30,
        auto_close=auto_close
    )
    
    # 结果
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到成交!")
        print(f"  弹窗信息: {info}")
    else:
        print("  ⚠️ 未检测到成交弹窗(30秒超时)")
    print(f"{'='*60}")
    
    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'target_code': target_code,
        'detected': detected,
        'info': info,
    }
    
    output_file = Path(__file__).parent / "popup_by_class_result.json"
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
