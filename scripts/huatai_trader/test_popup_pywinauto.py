"""
成交检测 - pywinauto UIA版 (推荐方案)

利用 Windows UIA 辅助接口穿透自绘控件，直接提取弹窗所有文字

优点:
- 无需截图、无识别误差
- 毫秒级捕获
- 支持自动关弹窗
- 可以读取自绘控件的文字

依赖:
    pip install pywinauto

使用方法:
    1. 运行脚本
    2. 在华泰执行买入
    3. 脚本自动检测成交弹窗并提取内容
"""

import time
import re
from datetime import datetime
from pathlib import Path
import json

# 记录已处理弹窗句柄，避免重复解析
handled_hwnd = set()


def find_xiadan_app():
    """连接华泰xiadan应用"""
    try:
        from pywinauto import Application
        
        # 尝试通过窗口标题连接
        try:
            app = Application(backend="uia").connect(title_re="网上股票交易系统5.0", timeout=3)
            print("✓ 通过窗口标题连接到 xiadan")
            return app
        except Exception as e1:
            print(f"  通过窗口标题连接失败: {e1}")
        
        # 尝试通过进程路径连接
        try:
            app = Application(backend="uia").connect(path=r"C:\htzq\xiadan.exe", timeout=3)
            print("✓ 通过进程路径连接到 xiadan")
            return app
        except Exception as e2:
            print(f"  通过进程路径连接失败: {e2}")
        
        # 尝试通过类名连接
        try:
            app = Application(backend="uia").connect(class_name_re="Afx.*", timeout=3)
            print("✓ 通过类名连接到 xiadan")
            return app
        except Exception as e3:
            print(f"  通过类名连接失败: {e3}")
        
        return None
        
    except ImportError:
        print("❌ 未安装 pywinauto")
        print("   请运行: pip install pywinauto")
        return None


def parse_trade_info(text):
    """
    提取买卖方向、代码、价格、数量
    
    根据实际弹窗格式:
    "成交回报 (帐号:张强)"
    "1) 10:51:39 买入 123270 价格:313.500元 数量: 10"
    """
    res = {}
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 解析主内容行 (如: "1) 10:51:39 买入 123270 价格:313.500元 数量: 10")
        # 使用正则表达式提取
        
        # 提取时间
        time_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
        if time_match:
            res["时间"] = time_match.group(1)
        
        # 提取买卖方向
        if "买入" in line:
            res["方向"] = "买入"
        elif "卖出" in line:
            res["方向"] = "卖出"
        
        # 提取证券代码 (6位数字)
        code_match = re.search(r'\b(\d{6})\b', line)
        if code_match:
            res["代码"] = code_match.group(1)
        
        # 提取价格 (格式: 价格:xxx元 或 价格:xxx.xxx元)
        price_match = re.search(r'价格[:：]\s*([\d.]+)', line)
        if price_match:
            res["成交价"] = price_match.group(1)
        
        # 提取数量 (格式: 数量: xxx 或 数量:xxx)
        qty_match = re.search(r'数量[:：]\s*(\d+)', line)
        if qty_match:
            res["股数"] = qty_match.group(1)
    
    return res


def monitor_xiadan_popup(target_code=None, timeout=30, auto_close=False):
    """
    监听华泰xiadan成交弹窗
    
    Args:
        target_code: 目标债券代码(可选，用于过滤)
        timeout: 监听超时(秒)
        auto_close: 是否自动关闭弹窗
        
    Returns:
        是否检测到成交
    """
    print("=" * 60)
    print("开始监听华泰 xiadan.exe 成交弹窗...")
    print("=" * 60)
    
    # 连接应用
    app = find_xiadan_app()
    if not app:
        print("❌ 无法连接到 xiadan，请确保软件已打开")
        return False, None
    
    print(f"\n  监听参数:")
    print(f"    目标代码: {target_code or '任意'}")
    print(f"    超时: {timeout}秒")
    print(f"    自动关闭弹窗: {auto_close}")
    print()
    
    start_time = time.time()
    detected = False
    detection_info = None
    
    while time.time() - start_time < timeout:
        try:
            # 尝试匹配标题含"成交"的弹窗
            # 根据实际弹窗图片: "成交回报 (帐号:张强)"
            popup_titles = ["成交回报", "成交提示", "委托回报", "提示", "通知"]
            
            for title_pattern in popup_titles:
                try:
                    popup = app.window(title=title_pattern, control_type="Window")
                    
                    # 检查窗口是否存在且可见
                    if popup.exists(timeout=0.1) and popup.is_visible():
                        hwnd = popup.handle
                        
                        # 避免重复处理同一弹窗
                        if hwnd in handled_hwnd:
                            continue
                        
                        handled_hwnd.add(hwnd)
                        
                        print(f"\n✓ 捕获到弹窗: \"{title_pattern}\" (句柄: {hwnd})")
                        print("-" * 60)
                        
                        # 获取弹窗内所有文本
                        all_texts = popup.texts()
                        full_content = "\n".join(all_texts)
                        
                        print("弹窗内容:")
                        print(full_content)
                        print("-" * 60)
                        
                        # 解析成交数据
                        trade_info = parse_trade_info(full_content)
                        
                        if trade_info:
                            print(f"解析成交数据: {trade_info}")
                            
                            # 检查是否匹配目标代码
                            if target_code and trade_info.get("代码") != target_code:
                                print(f"  代码不匹配 (目标: {target_code}, 实际: {trade_info.get('代码')})")
                                continue
                            
                            detected = True
                            detection_info = {
                                'title': title_pattern,
                                'hwnd': hwnd,
                                'content': full_content,
                                'parsed': trade_info,
                                'timestamp': datetime.now().isoformat(),
                            }
                            
                            # 自动关闭弹窗
                            if auto_close:
                                try:
                                    # 尝试点击确定按钮
                                    ok_btn = popup.window(title="确定", control_type="Button")
                                    if ok_btn.exists():
                                        ok_btn.click()
                                        print("  已自动点击[确定]关闭弹窗")
                                except Exception as e:
                                    print(f"  自动关闭弹窗失败: {e}")
                            
                            return detected, detection_info
                        
                except Exception:
                    # 该标题的弹窗不存在，继续下一个
                    continue
            
        except Exception as e:
            # 其他异常，记录但不中断
            if "uia" in str(e).lower():
                print(f"  UIA错误: {e}")
        
        # 每3秒打印一次状态
        elapsed = int(time.time() - start_time)
        if elapsed % 3 == 0 and elapsed > 0:
            print(f"  ... 已监听 {elapsed}秒 ...")
        
        time.sleep(0.3)
    
    print(f"\n  监听超时 ({timeout}秒)")
    return detected, detection_info


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交检测 - pywinauto UIA版 (推荐方案)                          ║
║                                                                  ║
║  利用 Windows UIA 辅助接口穿透自绘控件，直接提取弹窗所有文字     ║
║                                                                  ║
║  优点:                                                           ║
║  • 无需截图、无识别误差                                          ║
║  • 毫秒级捕获                                                    ║
║  • 支持自动关弹窗                                                ║
║  • 可以读取自绘控件的文字                                        ║
║                                                                  ║
║  依赖: pip install pywinauto                                     ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查依赖
    try:
        from pywinauto import Application
        print("✓ pywinauto 已安装")
    except ImportError:
        print("❌ 未安装 pywinauto")
        print("   请运行: pip install pywinauto")
        return
    
    # 输入目标代码
    target_code = input("\n  请输入要检测的债券代码(直接回车=检测任意): ").strip()
    
    # 是否自动关闭弹窗
    auto_close = input("  是否自动关闭弹窗? (y/n): ").strip().lower() == 'y'
    
    input("\n  请去华泰执行买入，按Enter开始监听...")
    
    # 开始监听
    detected, info = monitor_xiadan_popup(
        target_code=target_code or None,
        timeout=30,
        auto_close=auto_close
    )
    
    # 结果
    print(f"\n{'='*60}")
    if detected:
        print("  ✓ 检测到成交!")
        print(f"  弹窗标题: {info['title']}")
        print(f"  解析数据: {info['parsed']}")
    else:
        print("  ⚠️ 未检测到成交弹窗(30秒超时)")
        print("  可能原因:")
        print("    1. 买入未成交")
        print("    2. 弹窗标题不是预期的'成交提示'等")
        print("    3. 权限问题(脚本和xiadan权限不一致)")
    print(f"{'='*60}")
    
    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'target_code': target_code,
        'detected': detected,
        'info': info,
    }
    
    output_file = Path(__file__).parent / "popup_pywinauto_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")
    
    # 如果检测到，提供集成建议
    if detected:
        print("\n  下一步:")
        print("  1. 确认弹窗标题和内容格式")
        print("  2. 更新 auto_trader.py 使用此方案")
        print("  3. 测试完整交易流程")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  错误: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
