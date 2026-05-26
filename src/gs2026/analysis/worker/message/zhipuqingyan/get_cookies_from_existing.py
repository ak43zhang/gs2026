"""通过 CDP (Chrome DevTools Protocol) 连接已打开的 Edge/Chrome 浏览器获取 Cookies

使用方法:
1. 手动打开 Edge 浏览器
2. 访问智谱清言并完成验证
3. 在 Edge 地址栏输入: edge://version/ 查看"可执行文件路径"
4. 关闭所有 Edge 窗口
5. 使用命令行启动 Edge 并启用远程调试:
   
   "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222
   
   或者创建快捷方式，在目标后添加: --remote-debugging-port=9222
   
6. 访问智谱清言，完成验证
7. 运行此脚本获取 cookies
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# Cookies 存储路径
cookies_dir = Path(__file__).parent / 'cookies'
cookies_dir.mkdir(exist_ok=True)
cookies_file = cookies_dir / 'chatglm_cookies.json'

# CDP 连接地址
CDP_URL = 'http://localhost:9222'

def get_cookies_from_existing_browser():
    """从已打开的浏览器获取 cookies"""
    print("=" * 60)
    print("从已打开的浏览器获取 Cookies")
    print("=" * 60)
    print()
    
    print("前提条件:")
    print("1. Edge 已使用 --remote-debugging-port=9222 启动")
    print("2. 已完成智谱清言验证")
    print()
    
    input("确认已满足条件，按 Enter 键开始...")
    print()
    
    try:
        with sync_playwright() as p:
            print(f"正在连接 CDP: {CDP_URL}")
            
            # 连接到已存在的浏览器
            browser = p.chromium.connect_over_cdp(CDP_URL)
            
            print(f"✓ 已连接到浏览器")
            print(f"  上下文数量: {len(browser.contexts)}")
            
            # 获取默认上下文
            if not browser.contexts:
                print("✗ 没有找到浏览器上下文")
                return
            
            context = browser.contexts[0]
            
            # 获取所有页面
            pages = context.pages
            print(f"  页面数量: {len(pages)}")
            print()
            
            # 查找智谱清言页面
            target_page = None
            for page in pages:
                url = page.url
                title = page.title()
                print(f"  页面: {title[:30]}... | {url[:50]}...")
                if 'chatglm.cn' in url:
                    target_page = page
                    
            if not target_page:
                print()
                print("✗ 未找到智谱清言页面")
                print("请确保已在浏览器中打开 https://chatglm.cn")
                return
            
            print()
            print(f"✓ 找到智谱清言页面")
            
            # 获取 cookies
            cookies = context.cookies()
            
            if not cookies:
                print("✗ 未获取到 cookies")
                return
            
            # 筛选智谱清言相关的 cookies
            chatglm_cookies = [c for c in cookies if 'chatglm.cn' in c.get('domain', '')]
            
            print(f"✓ 获取到 {len(cookies)} 个 cookies")
            print(f"  其中智谱清言相关: {len(chatglm_cookies)} 个")
            print()
            
            # 保存到文件
            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            
            print(f"✓ 已保存到: {cookies_file}")
            print()
            print("Cookies 列表:")
            for cookie in chatglm_cookies[:10]:  # 只显示前10个
                name = cookie.get('name', 'unknown')
                value = cookie.get('value', '')
                preview = value[:30] + '...' if len(value) > 30 else value
                print(f"  - {name}: {preview}")
            
            if len(chatglm_cookies) > 10:
                print(f"  ... 还有 {len(chatglm_cookies) - 10} 个")
            
            print()
            print("=" * 60)
            print("完成！现在可以运行主程序了。")
            print("=" * 60)
            
    except Exception as e:
        print(f"✗ 错误: {e}")
        print()
        print("常见问题:")
        print("1. Edge 是否已使用 --remote-debugging-port=9222 启动?")
        print("2. 端口 9222 是否被占用?")
        print("3. 是否有防火墙阻止连接?")
        import traceback
        traceback.print_exc()

def show_setup_guide():
    """显示设置指南"""
    print()
    print("=" * 60)
    print("设置指南: 如何启用 Edge 远程调试")
    print("=" * 60)
    print()
    print("方法1: 命令行启动")
    print('  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222')
    print()
    print("方法2: 创建快捷方式")
    print("  1. 右键桌面 → 新建 → 快捷方式")
    print('  2. 位置: "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"')
    print("  3. 右键快捷方式 → 属性")
    print('  4. 在"目标"后添加: --remote-debugging-port=9222')
    print("  5. 使用此快捷方式启动 Edge")
    print()
    print("方法3: 修改注册表（永久生效）")
    print('  1. 运行 regedit')
    print('  2. 找到: HKEY_CLASSES_ROOT\Applications\msedge.exe\shell\open\command')
    print('  3. 修改默认值，在末尾添加: --remote-debugging-port=9222')
    print()
    print("验证是否成功:")
    print("  1. 使用上述方法启动 Edge")
    print("  2. 访问: http://localhost:9222/json")
    print("  3. 如果能看到 JSON 数据，说明成功")
    print()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'guide':
        show_setup_guide()
    else:
        get_cookies_from_existing_browser()
        input("\n按 Enter 键退出...")
