"""智谱清言全自动分析模式 - 模拟真人操作

特点:
- 全自动运行，无需人工干预
- 增加随机延迟和鼠标移动模拟真人
- 支持验证码自动检测和等待
- 支持失败重试
"""

import json
import time
import random
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, Page

CDP_URL = 'http://localhost:9222'

class ChatGLMFullAuto:
    """全自动智谱清言操作"""
    
    def __init__(self):
        self.browser = None
        self.page: Optional[Page] = None
        self.playwright = None
        
    def connect(self) -> bool:
        """连接到已打开的浏览器"""
        try:
            self.playwright = sync_playwright().start()
            print(f"[*] 连接浏览器: {CDP_URL}")
            self.browser = self.playwright.chromium.connect_over_cdp(CDP_URL)
            
            if not self.browser.contexts:
                print("[X] 无浏览器上下文")
                return False
            
            context = self.browser.contexts[0]
            
            # 查找智谱清言页面
            for page in context.pages:
                if 'chatglm.cn' in page.url:
                    self.page = page
                    print(f"[✓] 找到页面: {page.url[:50]}...")
                    return True
            
            # 没找到，创建新页面
            self.page = context.new_page()
            print("[✓] 创建新页面")
            return True
            
        except Exception as e:
            print(f"[X] 连接失败: {e}")
            return False
    
    def random_delay(self, min_sec: float = 0.5, max_sec: float = 2.0):
        """随机延迟"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
    
    def random_mouse_move(self):
        """随机鼠标移动"""
        try:
            if self.page:
                # 随机位置
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                self.page.mouse.move(x, y)
                self.random_delay(0.1, 0.3)
        except:
            pass
    
    def random_scroll(self):
        """随机滚动"""
        try:
            if self.page:
                scroll_y = random.randint(-100, 100)
                self.page.evaluate(f'window.scrollBy(0, {scroll_y})')
                self.random_delay(0.2, 0.5)
        except:
            pass
    
    def check_verification(self) -> bool:
        """检查是否需要验证"""
        try:
            content = self.page.content()
            keywords = ['Access Verification', '验证', 'Verification', '安全验证']
            need_verify = any(kw in content for kw in keywords)
            if need_verify:
                print("[!] 检测到验证页面")
            return need_verify
        except:
            return False
    
    def wait_for_verification(self, timeout: int = 300):
        """等待验证完成"""
        print(f"[*] 等待验证完成（最长 {timeout} 秒）...")
        start = time.time()
        
        while time.time() - start < timeout:
            if not self.check_verification():
                print("[✓] 验证已完成")
                return True
            
            # 随机活动
            self.random_mouse_move()
            if random.random() < 0.3:
                self.random_scroll()
            
            time.sleep(2)
        
        print("[X] 验证等待超时")
        return False
    
    def navigate(self) -> bool:
        """导航到智谱清言"""
        try:
            if 'chatglm.cn' not in self.page.url:
                print("[*] 访问智谱清言...")
                self.page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=60000)
                self.random_delay(3, 5)
            
            # 检查验证
            if self.check_verification():
                if not self.wait_for_verification():
                    return False
            
            print("[✓] 页面就绪")
            return True
            
        except Exception as e:
            print(f"[X] 导航失败: {e}")
            return False
    
    def close_popup(self):
        """关闭弹窗"""
        try:
            print("[*] 关闭弹窗...")
            
            # 尝试多种方式
            actions = [
                lambda: self.page.click('button:has-text("我知道了")', timeout=2000),
                lambda: self.page.press('body', 'Escape'),
                lambda: self.page.click('[class*="close"]', timeout=2000),
            ]
            
            for action in actions:
                try:
                    action()
                    self.random_delay(0.5, 1)
                except:
                    continue
            
            print("[✓] 弹窗处理完成")
            
        except Exception as e:
            print(f"[!] 弹窗处理: {e}")
    
    def start_new_chat(self) -> bool:
        """点击新对话"""
        try:
            print("[*] 创建新对话...")
            
            # 随机鼠标移动
            self.random_mouse_move()
            self.random_delay(0.5, 1)
            
            # 尝试点击
            selectors = [
                'div.new-session',
                'div.aside-subjects > div.new-session',
                '[class*="new-session"]',
            ]
            
            for selector in selectors:
                try:
                    # 先滚动到可见
                    self.page.locator(selector).scroll_into_view_if_needed(timeout=3000)
                    self.random_delay(0.3, 0.6)
                    
                    # 点击
                    self.page.click(selector, timeout=5000)
                    print(f"[✓] 已创建新对话 ({selector})")
                    self.random_delay(3, 5)
                    return True
                except:
                    continue
            
            print("[!] 未找到新对话按钮")
            return False
            
        except Exception as e:
            print(f"[X] 创建新对话失败: {e}")
            return False
    
    def enable_thinking(self):
        """启用思考模式"""
        try:
            print("[*] 启用思考模式...")
            
            self.random_mouse_move()
            self.random_delay(0.5, 1)
            
            selectors = [
                'button:has-text("思考")',
                '[class*="thinking"]',
            ]
            
            for selector in selectors:
                try:
                    self.page.click(selector, timeout=3000)
                    print("[✓] 思考模式已启用")
                    self.random_delay(1, 2)
                    return
                except:
                    continue
            
            print("[!] 未找到思考按钮")
            
        except Exception as e:
            print(f"[!] 启用思考模式: {e}")
    
    def enable_web_search(self):
        """启用联网搜索"""
        try:
            print("[*] 启用联网搜索...")
            
            self.random_mouse_move()
            self.random_delay(0.5, 1)
            
            selectors = [
                'button:has-text("联网")',
                '[class*="web-search"]',
            ]
            
            for selector in selectors:
                try:
                    self.page.click(selector, timeout=3000)
                    print("[✓] 联网搜索已启用")
                    self.random_delay(1, 2)
                    return
                except:
                    continue
            
            print("[!] 未找到联网按钮")
            
        except Exception as e:
            print(f"[!] 启用联网搜索: {e}")
    
    def send_message(self, message: str) -> bool:
        """发送消息（模拟真人输入）"""
        try:
            print(f"[*] 发送消息（{len(message)} 字符）...")
            
            # 找到输入框
            textarea = self.page.locator('textarea')
            
            # 随机点击
            self.random_mouse_move()
            textarea.click()
            self.random_delay(0.5, 1.5)
            
            # 分段输入，模拟真人打字
            chunk_size = random.randint(30, 80)
            for i in range(0, len(message), chunk_size):
                chunk = message[i:i+chunk_size]
                
                # 输入
                textarea.type(chunk, delay=random.randint(20, 60))
                
                # 随机停顿
                if random.random() < 0.3:
                    self.random_delay(0.2, 0.5)
                
                # 偶尔移动鼠标
                if random.random() < 0.2:
                    self.random_mouse_move()
            
            # 随机思考时间
            self.random_delay(1, 3)
            
            # 发送
            textarea.press('Enter')
            print("[✓] 消息已发送")
            
            return True
            
        except Exception as e:
            print(f"[X] 发送失败: {e}")
            return False
    
    def wait_for_response(self, timeout: int = 300) -> str:
        """等待回复"""
        print(f"[*] 等待回复（最长 {timeout} 秒）...")
        
        start = time.time()
        last_text = ""
        stable_count = 0
        
        while time.time() - start < timeout:
            try:
                # 随机活动
                if random.random() < 0.3:
                    self.random_mouse_move()
                if random.random() < 0.1:
                    self.random_scroll()
                
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
                                        print("[✓] 回复完成")
                                        return text
                                else:
                                    stable_count = 0
                                    last_text = text
                                    print(f"  收到 {len(text)} 字符...")
                    except:
                        continue
                
                time.sleep(2)
                
            except Exception as e:
                time.sleep(2)
        
        print("[!] 等待超时")
        return last_text
    
    def analyze(self, message: str) -> str:
        """完整分析流程"""
        print("=" * 60)
        print("智谱清言全自动分析")
        print("=" * 60)
        print()
        
        # 1. 连接
        if not self.connect():
            return ""
        
        # 2. 导航
        if not self.navigate():
            return ""
        
        # 3. 关闭弹窗
        self.close_popup()
        
        # 4. 创建新对话
        self.start_new_chat()
        
        # 5. 启用功能
        self.enable_thinking()
        self.enable_web_search()
        
        # 6. 发送消息
        if not self.send_message(message):
            return ""
        
        # 7. 获取回复
        result = self.wait_for_response()
        
        print()
        print("=" * 60)
        print(f"[✓] 完成，结果长度: {len(result)}")
        print("=" * 60)
        
        return result
    
    def close(self):
        """关闭连接"""
        try:
            if self.playwright:
                self.playwright.stop()
            print("[✓] 已断开连接")
        except:
            pass


def full_auto_analysis(message: str = None) -> str:
    """全自动分析入口"""
    
    if not message:
        message = """2026-05-20全球重要大事件集锦，按重要程度给出5条主领域为科技，子领域为AI的消息。
请返回JSON格式。"""
    
    bot = ChatGLMFullAuto()
    
    try:
        result = bot.analyze(message)
        return result
    finally:
        bot.close()


if __name__ == "__main__":
    result = full_auto_analysis()
    print("\n结果预览:")
    print(result[:500] + "..." if len(result) > 500 else result)
