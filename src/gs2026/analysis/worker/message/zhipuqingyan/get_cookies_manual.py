"""智谱清言 Cookies 手动获取工具

使用方法:
1. 运行脚本: python get_cookies_manual.py
2. 浏览器会自动打开智谱清言页面
3. 手动完成验证（如 Access Verification）
4. 按任意键保存 cookies
5. cookies 将保存到 cookies/chatglm_cookies.json

之后运行主程序时会自动加载这些 cookies。
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# 配置
cookies_dir = Path(__file__).parent / 'cookies'
cookies_dir.mkdir(exist_ok=True)
cookies_file = cookies_dir / 'chatglm_cookies.json'

# Firefox 路径（根据实际情况修改）
firefox_path = r'C:\Program Files\Mozilla Firefox\firefox.exe'

def get_cookies_manual():
    """手动获取 cookies"""
    print("=" * 60)
    print("智谱清言 Cookies 手动获取工具")
    print("=" * 60)
    print()
    print("步骤:")
    print("1. 浏览器将自动打开智谱清言页面")
    print("2. 请手动完成验证（如 Access Verification）")
    print("3. 完成后返回此窗口，按 Enter 键保存 cookies")
    print()
    input("按 Enter 键开始...")
    print()
    
    with sync_playwright() as p:
        # 启动浏览器（非无头模式，方便人工操作）
        print("正在启动浏览器...")
        browser = p.firefox.launch(
            headless=False,
            executable_path=firefox_path
        )
        
        # 创建上下文
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        
        page = context.new_page()
        
        # 访问智谱清言
        print("正在打开智谱清言页面...")
        page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=60000)
        print("页面已加载")
        print()
        
        # 等待用户完成验证
        print("请手动完成验证（如 Access Verification）")
        print("完成后返回此窗口，按 Enter 键保存 cookies")
        print()
        input("按 Enter 键保存 cookies...")
        print()
        
        # 获取并保存 cookies
        try:
            cookies = context.cookies()
            
            # 保存到文件
            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            
            print(f"✓ Cookies 已保存到: {cookies_file}")
            print(f"  共 {len(cookies)} 个 cookies")
            print()
            
            # 显示 cookies 信息
            print("Cookies 详情:")
            for cookie in cookies:
                print(f"  - {cookie.get('name', 'unknown')}: {cookie.get('domain', 'unknown')}")
            print()
            
        except Exception as e:
            print(f"✗ 保存 cookies 失败: {e}")
        
        # 关闭浏览器
        browser.close()
        print("浏览器已关闭")
        print()
        print("=" * 60)
        print("完成！现在可以运行主程序了。")
        print("=" * 60)

if __name__ == "__main__":
    get_cookies_manual()
