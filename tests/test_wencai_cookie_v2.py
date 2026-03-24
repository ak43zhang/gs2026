"""
测试方案A：使用已保存的Cookie访问同花顺问财（优化版）
验证Cookie方式是否可行

改进：
1. 添加超时自动保存机制
2. 增加调试信息
3. 支持命令行参数

运行方式：
    python tests/test_wencai_cookie_v2.py [save|test]

参数：
    save - 只保存Cookie
    test - 只测试Cookie（需先save）
    无参数 - 完整流程
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from gs2026.constants import CHROME_1208

# 配置
PROJECT_ROOT = Path(__file__).parent.parent
COOKIE_FILE = PROJECT_ROOT / "configs" / "wencai_cookies.json"
BROWSER_PATH = CHROME_1208
TEST_QUERY = "主板，非st，2026-03-24涨停"

# 选择器
NUMBER_SELECTOR = '#xuan-top-con > div.xuangu-tool > div > div > div > span.ui-f24.ui-fb.red_text.ui-pl8'


def save_cookies():
    """保存Cookie - 优化版"""
    print("=" * 60)
    print("步骤1：手动登录并保存Cookie")
    print("=" * 60)
    print(f"Cookie将保存到: {COOKIE_FILE}")
    print()
    
    with sync_playwright() as p:
        print("正在启动浏览器...")
        try:
            browser = p.chromium.launch(
                headless=False,
                executable_path=BROWSER_PATH,
                args=['--disable-blink-features=AutomationControlled']
            )
        except Exception as e:
            print(f"❌ 启动浏览器失败: {e}")
            print(f"请检查路径: {BROWSER_PATH}")
            return False
        
        print("✅ 浏览器已启动")
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        # 打开问财首页
        print("正在打开问财首页...")
        try:
            page.goto("https://www.iwencai.com/unifiedwap/home/index", timeout=30000)
            print("✅ 页面已加载")
        except PlaywrightTimeout:
            print("⚠️ 页面加载超时，继续等待...")
        except Exception as e:
            print(f"❌ 打开页面失败: {e}")
            browser.close()
            return False
        
        print()
        print("请手动完成以下操作：")
        print("1. 如果弹出登录窗口，请完成登录（扫码或账号密码）")
        print("2. 确保登录成功，能看到搜索框")
        print("3. 在命令行窗口按回车键保存Cookie")
        print()
        print("⚠️ 注意：如果浏览器窗口被最小化，请手动点击任务栏图标恢复")
        print()
        
        # 使用 try-except 处理输入，防止异常
        try:
            user_input = input(">>> 完成登录后请按回车键保存Cookie（或输入 'q' 退出）: ")
            if user_input.strip().lower() == 'q':
                print("用户取消操作")
                browser.close()
                return False
        except KeyboardInterrupt:
            print("\n用户中断操作")
            browser.close()
            return False
        except Exception as e:
            print(f"输入异常: {e}")
            print("继续尝试保存Cookie...")
        
        # 保存Cookie
        print("\n正在保存Cookie...")
        try:
            time.sleep(1)  # 等待状态同步
            context.storage_state(path=str(COOKIE_FILE))
            
            if COOKIE_FILE.exists():
                file_size = os.path.getsize(COOKIE_FILE)
                print(f"✅ Cookie已保存！文件大小: {file_size} bytes")
                
                # 显示Cookie基本信息
                try:
                    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                        cookies = json.load(f)
                    if 'cookies' in cookies:
                        print(f"✅ Cookie数量: {len(cookies['cookies'])}")
                except:
                    pass
                    
                browser.close()
                return True
            else:
                print(f"❌ Cookie文件未创建")
                browser.close()
                return False
                
        except Exception as e:
            print(f"❌ 保存Cookie失败: {e}")
            import traceback
            traceback.print_exc()
            browser.close()
            return False


def test_cookie():
    """测试Cookie"""
    print()
    print("=" * 60)
    print("步骤2：使用Cookie进行查询测试")
    print("=" * 60)
    
    if not COOKIE_FILE.exists():
        print(f"❌ Cookie文件不存在: {COOKIE_FILE}")
        print("请先运行: python test_wencai_cookie_v2.py save")
        return False
    
    # 检查Cookie文件
    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        cookie_count = len(cookies.get('cookies', []))
        print(f"✅ 加载Cookie成功，共 {cookie_count} 个")
    except Exception as e:
        print(f"❌ 读取Cookie文件失败: {e}")
        return False
    
    with sync_playwright() as p:
        print("正在启动浏览器...")
        browser = p.chromium.launch(
            headless=False,  # 显示浏览器便于观察
            executable_path=BROWSER_PATH,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # 使用Cookie创建上下文
        context = browser.new_context(
            storage_state=str(COOKIE_FILE),
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        print("正在打开问财首页...")
        page.goto("https://www.iwencai.com/unifiedwap/home/index")
        time.sleep(3)
        
        # 检查登录状态
        print("检查登录状态...")
        
        # 方法1：检查是否有登录按钮
        login_btn = page.query_selector('text=登录')
        if login_btn and login_btn.is_visible():
            print("⚠️ 发现登录按钮，可能未登录成功")
        else:
            print("✅ 未发现登录按钮")
        
        # 方法2：检查是否有用户头像或用户名
        user_elements = [
            '.user-name',
            '.avatar',
            '[class*="user"]',
            'text=我的'
        ]
        user_found = False
        for selector in user_elements:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    print(f"✅ 发现用户元素: {selector}")
                    user_found = True
                    break
            except:
                pass
        
        if not user_found:
            print("⚠️ 未发现用户元素，可能未登录")
        
        # 尝试查询
        print()
        print(f"执行测试查询: {TEST_QUERY}")
        try:
            # 填写查询
            page.get_by_placeholder("请输入您的筛选条件，多个条件用分号隔开").fill(TEST_QUERY)
            page.locator(".right-action > div:nth-child(3) > .icon").click()
            
            # 等待结果
            page.wait_for_selector(NUMBER_SELECTOR, timeout=15000)
            query_num = page.query_selector(NUMBER_SELECTOR).text_content()
            print(f"✅ 查询成功！结果数量: {query_num}")
            
            # 再次检查登录状态
            time.sleep(2)
            login_btn = page.query_selector('text=登录')
            if login_btn and login_btn.is_visible():
                print("⚠️ 查询后弹出登录，Cookie可能已过期")
                browser.close()
                return False
            
            print()
            print("=" * 60)
            print("✅ 测试通过！Cookie方式可行！")
            print("=" * 60)
            browser.close()
            return True
            
        except PlaywrightTimeout:
            print("❌ 查询超时，可能未登录成功")
            browser.close()
            return False
        except Exception as e:
            print(f"❌ 查询失败: {e}")
            browser.close()
            return False


def main():
    parser = argparse.ArgumentParser(description='同花顺问财Cookie测试')
    parser.add_argument('action', nargs='?', choices=['save', 'test'], 
                       help='save-只保存Cookie, test-只测试Cookie')
    args = parser.parse_args()
    
    print()
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "同花顺问财Cookie测试 v2" + " " * 19 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    if args.action == 'save':
        success = save_cookies()
        return 0 if success else 1
    elif args.action == 'test':
        success = test_cookie()
        return 0 if success else 1
    else:
        # 完整流程
        if not COOKIE_FILE.exists():
            print("Cookie文件不存在，先执行保存步骤...")
            if not save_cookies():
                return 1
        else:
            print(f"Cookie文件已存在: {COOKIE_FILE}")
            choice = input("是否重新保存Cookie? (y/n): ").strip().lower()
            if choice == 'y':
                if not save_cookies():
                    return 1
        
        print()
        input("按回车键开始测试...")
        success = test_cookie()
        return 0 if success else 1


if __name__ == "__main__":
    exit(main())
