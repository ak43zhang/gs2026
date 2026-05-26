"""智谱清言简化版全自动分析 - 按人为操作流程

流程:
1. 点击新对话
2. 关闭弹窗（如果出现）
3. 点击联网
4. 输入 query
5. 点击发送
6. 等待完成
7. 获取 JSON 数据
8. 保存入库
"""

import json
import time
import random
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, Page

CDP_URL = 'http://localhost:9222'

class ChatGLMSimple:
    """简化版智谱清言操作"""
    
    def __init__(self):
        self.browser = None
        self.page: Optional[Page] = None
        self.playwright = None
        
    def connect(self) -> bool:
        """连接到已打开的浏览器"""
        try:
            self.playwright = sync_playwright().start()
            print("[*] 连接浏览器...")
            self.browser = self.playwright.chromium.connect_over_cdp(CDP_URL)
            
            if not self.browser.contexts:
                print("[X] 无浏览器上下文")
                return False
            
            context = self.browser.contexts[0]
            
            # 查找智谱清言页面
            for page in context.pages:
                if 'chatglm.cn' in page.url:
                    self.page = page
                    print(f"[✓] 找到页面")
                    return True
            
            # 没找到，创建新页面
            self.page = context.new_page()
            self.page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=60000)
            print("[✓] 创建新页面并访问")
            return True
            
        except Exception as e:
            print(f"[X] 连接失败: {e}")
            return False
    
    def random_sleep(self, min_sec=1, max_sec=3):
        """随机等待"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def start_new_chat(self) -> bool:
        """1. 点击新对话"""
        try:
            print("[*] 步骤1: 点击新对话...")
            
            # 滚动到可见并点击
            element = self.page.locator('div.new-session')
            element.scroll_into_view_if_needed()
            self.random_sleep(0.5, 1)
            
            element.click(timeout=5000)
            print("[✓] 已点击新对话")
            self.random_sleep(2, 3)
            return True
            
        except Exception as e:
            print(f"[X] 点击新对话失败: {e}")
            return False
    
    def close_popup(self) -> bool:
        """关闭弹窗（通用）"""
        try:
            print("[*] 检查并关闭弹窗...")
            
            # 尝试多种关闭方式
            close_methods = [
                lambda: self.page.click('button:has-text("我知道了")', timeout=2000),
                lambda: self.page.click('[class*="close"]', timeout=2000),
                lambda: self.page.press('body', 'Escape'),
            ]
            
            popup_closed = False
            for method in close_methods:
                try:
                    method()
                    popup_closed = True
                    print("[✓] 已关闭弹窗")
                    self.random_sleep(0.5, 1)
                    break
                except:
                    continue
            
            if not popup_closed:
                print("[!] 无弹窗或关闭失败")
            
            return True
            
        except Exception as e:
            print(f"[!] 关闭弹窗: {e}")
            return True  # 继续执行
    
    def close_second_popup(self) -> bool:
        """关闭第二次弹窗（新对话后）"""
        try:
            print("[*] 关闭第二次弹窗...")
            
            # 使用特定选择器
            selectors = [
                '#maasGuidePopover svg',
                '#maasGuidePopover .close-btn-container svg',
            ]
            
            for selector in selectors:
                try:
                    self.page.click(selector, timeout=3000)
                    print(f"[✓] 已关闭第二次弹窗: {selector}")
                    self.random_sleep(0.5, 1)
                    return True
                except:
                    continue
            
            # 如果特定选择器失败，使用通用方法
            print("[!] 特定选择器失败，使用通用方法")
            return self.close_popup()
            
        except Exception as e:
            print(f"[!] 关闭第二次弹窗: {e}")
            return True
    
    def enable_web_search(self) -> bool:
        """3. 点击联网"""
        try:
            print("[*] 步骤3: 点击联网...")
            
            # 使用用户提供的特定选择器
            try:
                selector = '#search-input-box .session-button-container > div:nth-child(2) > span'
                self.page.click(selector, timeout=5000)
                print(f"[✓] 已点击联网 ({selector})")
                self.random_sleep(1, 2)
                return True
            except:
                pass
            
            # 备选选择器
            selectors = [
                '#search-input-box span:has-text("联网")',
                '.session-button-container > div:nth-child(2)',
                'button:has-text("联网")',
            ]
            
            for selector in selectors:
                try:
                    self.page.click(selector, timeout=3000)
                    print(f"[✓] 已点击联网 ({selector})")
                    self.random_sleep(1, 2)
                    return True
                except:
                    continue
            
            # 最后备选：使用 first
            try:
                self.page.get_by_text('联网', exact=False).first.click()
                print("[✓] 已点击联网 (first)")
                self.random_sleep(1, 2)
                return True
            except:
                pass
            
            print("[X] 点击联网失败")
            return False
            
        except Exception as e:
            print(f"[X] 点击联网失败: {e}")
            return False
    
    def check_and_close_login_popup(self) -> bool:
        """检查并关闭登录弹窗"""
        try:
            page_content = self.page.content()
            login_keywords = ['登录', '手机号登录', '微信登录']
            
            is_login_popup = any(kw in page_content for kw in login_keywords)
            
            if is_login_popup:
                print("[!] 检测到登录弹窗，尝试关闭...")
                
                close_selectors = [
                    '[class*="close"]',
                    'button[class*="close"]',
                ]
                
                for selector in close_selectors:
                    try:
                        self.page.click(selector, timeout=2000)
                        print(f"[✓] 已关闭登录弹窗")
                        time.sleep(1)
                        return True
                    except:
                        continue
                
                # 尝试 ESC
                try:
                    self.page.press('body', 'Escape')
                    print("[✓] 已关闭登录弹窗 (ESC)")
                    time.sleep(1)
                    return True
                except:
                    pass
                
                return False
            
            return True
            
        except:
            return True
    
    def send_query(self, query: str) -> bool:
        """4. 输入 query 并发送（一次性粘贴）"""
        try:
            print(f"[*] 步骤4: 填入消息（{len(query)} 字符）...")
            
            # 找到输入框
            textarea = self.page.locator('#search-input-box textarea')
            
            # 点击输入框获取焦点
            textarea.click()
            self.random_sleep(0.3, 0.8)
            
            # 一次性填入消息
            try:
                textarea.fill(query)
                print("[✓] 消息已填入")
            except Exception as e:
                print(f"[!] fill失败，使用evaluate: {e}")
                # 备选：通过 evaluate 设置
                self.page.evaluate(f'''() => {{
                    const textarea = document.querySelector('#search-input-box textarea');
                    if (textarea) {{
                        textarea.value = {json.dumps(query)};
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}''')
                print("[✓] 消息已通过 evaluate 填入")
            
            # 停顿（模拟查看内容）
            self.random_sleep(1, 2)
            
            # 5. 点击执行按钮
            print("[*] 步骤5: 点击执行按钮...")
            send_selector = '#search-input-box .enter.is-main-chat img'
            
            try:
                self.page.click(send_selector, timeout=5000)
                print("[✓] 已点击执行按钮")
            except:
                textarea.press('Enter')
                print("[✓] 已发送（回车）")
            
            # 6. 检查登录弹窗
            time.sleep(1)
            if not self.check_and_close_login_popup():
                print("[!] 登录弹窗未关闭，重新发送...")
                
                # 重新填入
                textarea = self.page.locator('#search-input-box textarea')
                textarea.click()
                self.random_sleep(0.3, 0.8)
                
                # 清空并重新填入
                textarea.fill('')
                self.random_sleep(0.3, 0.5)
                textarea.fill(query)
                self.random_sleep(1, 2)
                
                try:
                    self.page.click(send_selector, timeout=5000)
                    print("[✓] 已重新发送")
                except:
                    textarea.press('Enter')
                    print("[✓] 已重新发送（回车）")
            
            return True
            
        except Exception as e:
            print(f"[X] 发送失败: {e}")
            return False
    
    def wait_for_complete(self, timeout=300) -> str:
        """6. 等待执行完成并获取数据"""
        print(f"[*] 步骤6: 等待回复（最长 {timeout} 秒）...")
        
        start = time.time()
        last_text = ""
        stable_count = 0
        
        while time.time() - start < timeout:
            try:
                # 获取回复
                selectors = ['.markdown-body', '.chat-content', '[class*="response"]']
                
                for selector in selectors:
                    try:
                        element = self.page.locator(selector).last
                        if element.count() > 0:
                            text = element.inner_text()
                            if text and len(text) > 100:
                                # 检查是否稳定
                                if text == last_text:
                                    stable_count += 1
                                    if stable_count >= 3:
                                        print(f"[✓] 回复完成（{len(text)} 字符）")
                                        return text
                                else:
                                    stable_count = 0
                                    last_text = text
                                    print(f"  收到 {len(text)} 字符...")
                    except:
                        continue
                
                self.random_sleep(2, 3)
                
            except Exception as e:
                self.random_sleep(2, 3)
        
        print("[!] 等待超时")
        return last_text
    
    def analyze(self, query: str) -> str:
        """完整分析流程"""
        print("=" * 60)
        print("智谱清言简化版全自动分析")
        print("=" * 60)
        print()
        
        # 连接
        if not self.connect():
            return ""
        
        # 1. 关闭第一次弹窗（访问页面后）
        self.close_popup()
        
        # 2. 点击新对话
        if not self.start_new_chat():
            return ""
        
        # 3. 关闭第二次弹窗（新对话后）- 使用特定选择器
        self.close_second_popup()
        
        # 4. 点击联网
        if not self.enable_web_search():
            return ""
        
        # 4-5. 输入并发送
        if not self.send_query(query):
            return ""
        
        # 6. 等待完成
        result = self.wait_for_complete()
        
        print()
        print("=" * 60)
        print(f"[✓] 分析完成，结果长度: {len(result)}")
        print("=" * 60)
        
        return result
    
    def close(self):
        """关闭"""
        try:
            if self.playwright:
                self.playwright.stop()
            print("[✓] 已断开连接")
        except:
            pass


def simple_analysis(query: str = None) -> str:
    """简化版分析入口"""
    
    if not query:
        query = """2026-05-20全球重要大事件集锦，按重要程度给出5条主领域为科技，子领域为AI的消息。
请返回JSON格式。"""
    
    bot = ChatGLMSimple()
    
    try:
        result = bot.analyze(query)
        return result
    finally:
        bot.close()


if __name__ == "__main__":
    result = simple_analysis()
    print("\n结果预览:")
    print(result[:500] + "..." if len(result) > 500 else result)
