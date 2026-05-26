"""验证 Cookies 是否有效

使用方法:
python verify_cookies.py
"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

cookies_dir = Path(__file__).parent / 'cookies'
cookies_file = cookies_dir / 'chatglm_cookies.json'

# Edge 路径
EDGE_PATHS = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]

def find_edge():
    """查找 Edge"""
    for path in EDGE_PATHS:
        if Path(path).exists():
            return path
    return None

def verify_cookies():
    """验证 cookies"""
    print("=" * 60)
    print("验证 Cookies 有效性")
    print("=" * 60)
    print()
    
    if not cookies_file.exists():
        print(f"✗ Cookies 文件不存在: {cookies_file}")
        print("请先运行 get_cookies_from_edge.py 获取 cookies")
        return False
    
    with open(cookies_file, 'r') as f:
        cookies = json.load(f)
    
    print(f"✓ 加载了 {len(cookies)} 个 cookies")
    print()
    
    edge_path = find_edge()
    if not edge_path:
        print("✗ 未找到 Edge 浏览器")
        return False
    
    print(f"使用 Edge: {edge_path}")
    print()
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,  # 非无头模式，方便查看
                executable_path=edge_path
            )
            
            context = browser.new_context()
            context.add_cookies(cookies)
            
            page = context.new_page()
            
            print("正在访问智谱清言...")
            page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=30000)
            
            # 等待页面加载
            time.sleep(3)
            
            # 检查是否出现验证页面
            content = page.content()
            title = page.title()
            
            print(f"页面标题: {title}")
            print()
            
            verification_keywords = ['Access Verification', '验证', 'Verification', '安全检查']
            is_verification = any(keyword in content or keyword in title for keyword in verification_keywords)
            
            if is_verification:
                print("✗ Cookies 无效，仍需要验证")
                print()
                print("建议:")
                print("1. 重新运行 get_cookies_from_edge.py 获取新的 cookies")
                print("2. 确保在 Edge 中已完成验证")
                return False
            else:
                print("✓ Cookies 有效，无需验证！")
                print()
                print("可以正常使用主程序了。")
                return True
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 验证出错: {e}")
        return False

if __name__ == "__main__":
    import time
    verify_cookies()
    input("\n按 Enter 键退出...")
