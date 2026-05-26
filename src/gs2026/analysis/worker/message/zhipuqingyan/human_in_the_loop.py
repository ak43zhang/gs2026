"""人机协作模式 - 最简单可靠的方案

流程:
1. 你手动打开 Edge，完成验证
2. 程序截图显示当前页面状态
3. 你确认页面已就绪
4. 程序发送消息
5. 程序等待回复
6. 程序获取回复并保存

特点:
- 完全复用你的已验证浏览器
- 程序只操作页面，不处理验证
- 最稳定可靠
"""

import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP_URL = 'http://localhost:9222'

def human_in_the_loop_analysis():
    """人机协作分析"""
    print("=" * 60)
    print("人机协作模式 - 智谱清言分析")
    print("=" * 60)
    print()
    print("请按以下步骤操作:")
    print()
    print("1. 手动打开 Edge 浏览器")
    print("2. 访问: https://chatglm.cn/main/alltoolsdetail?lang=zh")
    print("3. 完成 Access Verification 验证")
    print("4. 确保页面显示正常（能看到输入框）")
    print("5. 保持浏览器窗口可见（不要最小化）")
    print()
    input("完成上述步骤后，按 Enter 键继续...")
    print()
    
    with sync_playwright() as p:
        print(f"正在连接浏览器: {CDP_URL}")
        
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"✗ 连接失败: {e}")
            print()
            print("请确保 Edge 已使用 --remote-debugging-port=9222 启动")
            return
        
        print("✓ 已连接")
        print()
        
        # 查找智谱清言页面
        target_page = None
        for context in browser.contexts:
            for page in context.pages:
                print(f"  发现页面: {page.url[:60]}...")
                if 'chatglm.cn' in page.url:
                    target_page = page
        
        if not target_page:
            print("✗ 未找到智谱清言页面")
            print("请在 Edge 中打开 https://chatglm.cn")
            return
        
        print(f"✓ 已找到智谱清言页面")
        print()
        
        # 检查页面状态
        print("检查页面状态...")
        try:
            # 尝试找到输入框
            textarea = target_page.locator('textarea')
            if textarea.count() == 0:
                print("✗ 未找到输入框，页面可能未就绪")
                print("请确保页面完全加载")
                return
            
            print("✓ 页面已就绪")
            print()
            
        except Exception as e:
            print(f"✗ 页面检查失败: {e}")
            return
        
        # 点击新对话
        print("正在创建新对话...")
        try:
            # 使用用户提供的选择器
            try:
                target_page.click('div.new-session', timeout=5000)
                print("✓ 已创建新对话 (div.new-session)")
                time.sleep(3)
            except:
                # 备选选择器
                selectors = [
                    'div.aside-subjects > div.new-session',
                    '[class*="new-session"]',
                    'button:has-text("新对话")',
                    'div:has-text("新对话")',
                ]
                for selector in selectors:
                    try:
                        target_page.click(selector, timeout=3000)
                        print(f"✓ 已创建新对话 ({selector})")
                        time.sleep(3)
                        break
                    except:
                        continue
                else:
                    print("⚠ 未找到新对话按钮，可能已在对话中")
        except Exception as e:
            print(f"⚠ 创建新对话失败: {e}")
        
        print()
        
        # 准备消息
        message = """2026-05-20全球重要大事件集锦，按重要程度给出5条主领域为科技，子领域为AI的消息。
请返回JSON格式，包含：关键事件、简要描述、重要程度评分、业务影响维度评分、综合评分、利空利好、消息大小、涉及板块、涉及概念、股票代码、时间、事件来源、原因分析、深度分析。"""
        
        print(f"准备发送消息（长度: {len(message)}）")
        print()
        input("确认要发送消息？按 Enter 键发送...")
        print()
        
        # 发送消息
        try:
            print("正在发送...")
            textarea = target_page.locator('textarea')
            textarea.fill(message)
            time.sleep(1)
            textarea.press('Enter')
            print("✓ 消息已发送")
            print()
        except Exception as e:
            print(f"✗ 发送失败: {e}")
            return
        
        # 等待回复
        print("等待回复（请观察浏览器窗口）...")
        print("当看到回复完成后，按 Enter 键获取结果")
        print()
        input("按 Enter 键获取回复...")
        print()
        
        # 获取回复
        try:
            print("正在获取回复...")
            
            # 尝试多种选择器
            selectors = ['.markdown-body', '.chat-content', '[class*="response"]']
            result = ""
            
            for selector in selectors:
                try:
                    element = target_page.locator(selector).last
                    if element.count() > 0:
                        result = element.inner_text()
                        if len(result) > 100:
                            break
                except:
                    continue
            
            if result:
                print(f"✓ 获取成功（{len(result)} 字符）")
                print()
                print("=" * 60)
                print("回复内容:")
                print("=" * 60)
                print(result[:1000])
                if len(result) > 1000:
                    print(f"... ({len(result) - 1000} 字符省略)")
                print()
                
                # 保存结果
                result_file = Path(__file__).parent / 'last_result.txt'
                with open(result_file, 'w', encoding='utf-8') as f:
                    f.write(result)
                print(f"✓ 结果已保存到: {result_file}")
                
            else:
                print("✗ 未能获取回复")
                
        except Exception as e:
            print(f"✗ 获取失败: {e}")
        
        print()
        print("=" * 60)
        print("完成！")
        print("=" * 60)

if __name__ == "__main__":
    human_in_the_loop_analysis()
    input("\n按 Enter 键退出...")
