"""使用 Microsoft Edge 获取智谱清言 Cookies

使用方法:
1. 确保已安装 Edge 浏览器
2. 运行: python get_cookies_from_edge.py
3. Edge 会自动打开智谱清言页面
4. 手动完成验证（如 Access Verification）
5. 完成后返回命令行，按 Enter 保存 cookies
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# Cookies 存储路径
cookies_dir = Path(__file__).parent / 'cookies'
cookies_dir.mkdir(exist_ok=True)
cookies_file = cookies_dir / 'chatglm_cookies.json'

# Edge 浏览器路径（根据实际情况修改）
EDGE_PATHS = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Users\' + os.environ.get('USERNAME', '') + r'\AppData\Local\Microsoft\Edge\Application\msedge.exe',
]

def find_edge():
    """查找 Edge 浏览器路径"""
    import os
    for path in EDGE_PATHS:
        if Path(path).exists():
            return path
    
    # 尝试从注册表查找
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe')
        edge_path, _ = winreg.QueryValueEx(key, '')
        return edge_path
    except:
        pass
    
    return None

def get_cookies_from_edge():
    """使用 Edge 获取 cookies"""
    print("=" * 60)
    print("使用 Microsoft Edge 获取智谱清言 Cookies")
    print("=" * 60)
    print()
    
    # 查找 Edge
    edge_path = find_edge()
    if not edge_path:
        print("✗ 未找到 Edge 浏览器，请手动指定路径")
        edge_path = input("请输入 Edge 路径: ").strip()
        if not edge_path or not Path(edge_path).exists():
            print("✗ 路径无效")
            return
    
    print(f"✓ 找到 Edge: {edge_path}")
    print()
    print("步骤:")
    print("1. Edge 浏览器将自动打开")
    print("2. 请手动完成验证（如 Access Verification）")
    print("3. 完成后返回此窗口，按 Enter 键保存 cookies")
    print()
    input("按 Enter 键开始...")
    print()
    
    try:
        with sync_playwright() as p:
            print("正在启动 Edge...")
            browser = p.chromium.launch(
                headless=False,
                executable_path=edge_path,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
            )
            
            page = context.new_page()
            
            print("正在打开智谱清言...")
            page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=60000)
            print("✓ 页面已加载")
            print()
            
            # 检查是否需要验证
            content = page.content()
            if 'Access Verification' in content or '验证' in content:
                print("⚠ 检测到验证页面，请手动完成验证")
            else:
                print("✓ 无需验证")
            
            print()
            print("请手动完成验证（如需要）")
            print("完成后返回此窗口，按 Enter 键保存 cookies")
            print()
            input("按 Enter 键保存 cookies...")
            print()
            
            # 获取 cookies
            cookies = context.cookies()
            
            if not cookies:
                print("✗ 未获取到 cookies")
                browser.close()
                return
            
            # 保存到文件
            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            
            print(f"✓ 已保存 {len(cookies)} 个 cookies")
            print(f"  文件: {cookies_file}")
            print()
            print("Cookies 列表:")
            for cookie in cookies:
                name = cookie.get('name', 'unknown')
                value = cookie.get('value', '')
                preview = value[:40] + '...' if len(value) > 40 else value
                print(f"  - {name}: {preview}")
            
            browser.close()
            print()
            print("=" * 60)
            print("完成！现在可以运行主程序了。")
            print()
            print("使用方式:")
            print("1. 在配置中设置 browser_type = 'edge'")
            print("2. 运行: python zhipuqingyan_analysis_event_driven.py")
            print("=" * 60)
            
    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import os
    get_cookies_from_edge()
