"""智谱清言半自动分析 - 用户手动保持浏览器验证，程序只发送消息

使用方法:
1. 手动打开 Edge 浏览器
2. 访问 https://chatglm.cn/main/alltoolsdetail?lang=zh
3. 完成 Access Verification 验证
4. 保持浏览器打开
5. 运行此脚本，它会连接到你的浏览器并发送分析请求

原理:
- 使用 Playwright 的 connect_over_cdp 连接到已打开的浏览器
- 复用已验证的浏览器会话
- 程序只负责发送消息和获取回复
"""

import json
import time
import random
from pathlib import Path
from typing import List, Tuple
from playwright.sync_api import sync_playwright

# CDP 连接地址（默认端口 9222）
CDP_URL = 'http://localhost:9222'

# 等待用户操作后按 Enter 继续
def wait_for_user(message: str = "按 Enter 键继续..."):
    print()
    input(message)
    print()

class ChatGLMManualBrowser:
    """连接已手动验证的浏览器"""
    
    def __init__(self):
        self.browser = None
        self.page = None
        self.playwright = None
        
    def connect(self) -> bool:
        """连接到已打开的浏览器"""
        try:
            self.playwright = sync_playwright().start()
            
            print(f"正在连接浏览器 CDP: {CDP_URL}")
            self.browser = self.playwright.chromium.connect_over_cdp(CDP_URL)
            
            # 获取默认上下文
            if not self.browser.contexts:
                print("✗ 没有找到浏览器上下文")
                return False
            
            context = self.browser.contexts[0]
            
            # 查找或创建智谱清言页面
            target_page = None
            for page in context.pages:
                if 'chatglm.cn' in page.url:
                    target_page = page
                    break
            
            if target_page:
                self.page = target_page
                print(f"✓ 已连接到智谱清言页面: {self.page.url[:60]}...")
            else:
                # 创建新页面
                self.page = context.new_page()
                print("✓ 已创建新页面")
            
            return True
            
        except Exception as e:
            print(f"✗ 连接失败: {e}")
            print()
            print("请确保:")
            print("1. Edge 已使用 --remote-debugging-port=9222 启动")
            print("2. 已完成智谱清言验证")
            return False
    
    def navigate_to_chatglm(self) -> bool:
        """导航到智谱清言"""
        try:
            if 'chatglm.cn' not in self.page.url:
                print("正在访问智谱清言...")
                self.page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=60000)
                time.sleep(3)
            
            # 检查是否需要验证
            content = self.page.content()
            if 'Access Verification' in content or '验证' in content:
                print("⚠ 需要完成验证")
                print("请在浏览器中完成验证，然后按 Enter 键")
                wait_for_user()
            
            print("✓ 已就绪")
            return True
            
        except Exception as e:
            print(f"✗ 导航失败: {e}")
            return False
    
    def start_new_chat(self) -> None:
        """点击新对话"""
        try:
            # 使用用户提供的选择器
            try:
                self.page.click('div.new-session', timeout=5000)
                print("✓ 已创建新对话 (div.new-session)")
                time.sleep(3)
                return
            except:
                pass
            
            # 备选选择器
            selectors = [
                'div.aside-subjects > div.new-session',
                '[class*="new-session"]',
                'button:has-text("新对话")',
                'div:has-text("新对话")',
            ]
            
            for selector in selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.click(selector)
                        print(f"✓ 已创建新对话 ({selector})")
                        time.sleep(3)
                        return
                except:
                    continue
            
            # 尝试 XPath
            try:
                self.page.locator('xpath=//div[contains(@class, "new-session")]').click(timeout=3000)
                print("✓ 已创建新对话 (XPath)")
                time.sleep(3)
                return
            except:
                pass
                    
        except Exception as e:
            print(f"创建新对话失败: {e}")
    
    def enable_thinking(self) -> None:
        """启用思考模式"""
        try:
            # 尝试点击"思考"按钮
            selectors = [
                'button:has-text("思考")',
                '[class*="thinking"]',
                'button[data-testid*="thinking"]'
            ]
            
            for selector in selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.click(selector)
                        print("✓ 已启用思考模式")
                        time.sleep(0.5)
                        return
                except:
                    continue
                    
        except Exception as e:
            print(f"启用思考模式失败: {e}")
    
    def enable_web_search(self) -> None:
        """启用联网搜索"""
        try:
            selectors = [
                'button:has-text("联网")',
                '[class*="web-search"]',
                'button[data-testid*="search"]'
            ]
            
            for selector in selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.click(selector)
                        print("✓ 已启用联网搜索")
                        time.sleep(0.5)
                        return
                except:
                    continue
                    
        except Exception as e:
            print(f"启用联网搜索失败: {e}")
    
    def send_message(self, query: str) -> None:
        """发送消息"""
        try:
            print(f"正在发送消息（长度: {len(query)}）...")
            
            # 找到输入框
            textarea = self.page.locator('textarea')
            
            # 点击输入框
            textarea.click()
            time.sleep(0.5)
            
            # 模拟人工输入
            chunk_size = 100
            for i in range(0, len(query), chunk_size):
                chunk = query[i:i+chunk_size]
                textarea.type(chunk, delay=random.randint(30, 80))
                time.sleep(random.uniform(0.1, 0.3))
            
            # 发送
            textarea.press('Enter')
            print("✓ 消息已发送")
            
        except Exception as e:
            print(f"✗ 发送失败: {e}")
            raise
    
    def wait_for_response(self, timeout: int = 300) -> str:
        """等待回复"""
        print(f"等待回复（最长 {timeout} 秒）...")
        
        start_time = time.time()
        last_text = ""
        stable_count = 0
        
        while time.time() - start_time < timeout:
            try:
                # 尝试获取回复内容
                selectors = ['.markdown-body', '.chat-content', '[class*="response"]']
                
                for selector in selectors:
                    try:
                        element = self.page.locator(selector).last
                        if element.count() > 0:
                            text = element.inner_text()
                            if text and len(text) > 100:
                                # 检查内容是否稳定
                                if text == last_text:
                                    stable_count += 1
                                    if stable_count >= 3:  # 连续3次相同，认为完成
                                        print("✓ 回复完成")
                                        return text
                                else:
                                    stable_count = 0
                                    last_text = text
                                    print(f"  收到回复... ({len(text)} 字符)")
                    except:
                        continue
                
                time.sleep(2)
                
            except Exception as e:
                print(f"等待出错: {e}")
                time.sleep(2)
        
        print("⚠ 等待超时，返回当前内容")
        return last_text
    
    def close(self) -> None:
        """关闭连接（不关闭浏览器）"""
        try:
            if self.playwright:
                self.playwright.stop()
            print("✓ 已断开连接")
        except Exception as e:
            print(f"断开连接失败: {e}")


def build_prompt(t_date: str, main_area: str, child_area: str, 
                 bk_dic_str: str, gn_dic_str: str) -> str:
    """构造 Prompt（简化版）"""
    query = f"{t_date}全球重要大事件集锦，按重要程度给出30条主领域为{main_area}，子领域为{child_area}的消息，" + """
重要程度评分：按照 权威性与级别 角度评估程度分为 国家级政策（5分）、部委/地方政策（4分）、行业会议（3分）、公司公告（2分）、市场传闻（1分）。按照 新颖性与想象力 角度评估程度分为 新技术/新政策（5分）、现有产业数据向好（3分）。按照 相关性与纯度 角度评估程度分为 直接受益（核心业务高度相关）（5分）、间接受益（产业链上下游）（3分）、情绪相关（概念沾边）（1分），最终由三者分数相加，总分范围0至15分。
业务影响维度评分：（每个维度-5至5分，总分范围-60至60）
    从12个关键经营维度评估消息的实质性影响，正面影响为正分，负面影响为负分，无影响为0分。
    按照 成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降 等维度评估。
综合评分：（通过重要程度评分×4+业务影响维度评分）。
利空利好（由业务影响维度评分和综合评分分析得出）。
消息大小（由综合评分计算得出，重大：90 ≤ 综合评分，大：60 ≤ 综合评分 < 90，中：30 ≤ 综合评分 < 60，小：综合评分 < 30）。
涉及板块（板块字典："""+bk_dic_str+"""）。
涉及概念（概念字典："""+gn_dic_str+"""）。
股票代码（请分析该消息直接受益或者受损的a股沪深板块股票代码）。
时间（事件发表最早的时间，格式yyyy-MM-dd HH:mm:ss）。
事件来源（事件最早时间的来源）。
原因分析（分析该消息对a股具体股票代码直接受益或者受损的原因）。
深度分析：(根据多个维度分析该消息的实质性影响)。
返回结果为json对象。
"""
    return query


def manual_analysis(t_date: str, main_area: str, child_area: str) -> str:
    """半自动分析 - 连接已验证的浏览器"""
    print("=" * 60)
    print("智谱清言半自动分析")
    print("=" * 60)
    print()
    print("前提条件:")
    print("1. Edge 已使用 --remote-debugging-port=9222 启动")
    print("2. 已完成智谱清言验证")
    print()
    
    # 构建 prompt
    bk_dic_str = "半导体,新能源,人工智能,医药,消费,金融,地产,汽车,电子,通信"
    gn_dic_str = "ChatGPT,大模型,算力,芯片,机器人,自动驾驶,元宇宙,区块链"
    query = build_prompt(t_date, main_area, child_area, bk_dic_str, gn_dic_str)
    
    print(f"分析日期: {t_date}")
    print(f"主领域: {main_area}")
    print(f"子领域: {child_area}")
    print(f"Prompt 长度: {len(query)}")
    print()
    
    # 连接浏览器
    browser = ChatGLMManualBrowser()
    
    if not browser.connect():
        return None
    
    try:
        # 导航到智谱清言
        if not browser.navigate_to_chatglm():
            return None
        
        # 创建新对话
        browser.start_new_chat()
        
        # 启用功能
        browser.enable_thinking()
        browser.enable_web_search()
        
        # 发送消息
        browser.send_message(query)
        
        # 等待回复
        result = browser.wait_for_response(timeout=300)
        
        print()
        print("=" * 60)
        print("分析完成")
        print("=" * 60)
        print(f"结果长度: {len(result)}")
        print()
        
        return result
        
    finally:
        browser.close()


def show_setup_guide():
    """显示设置指南"""
    print()
    print("=" * 60)
    print("设置指南")
    print("=" * 60)
    print()
    print("步骤1: 关闭所有 Edge 窗口")
    print()
    print("步骤2: 使用命令行启动 Edge")
    print('  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222')
    print()
    print("步骤3: 访问智谱清言")
    print("  地址栏输入: https://chatglm.cn/main/alltoolsdetail?lang=zh")
    print()
    print("步骤4: 完成验证")
    print("  如果出现 Access Verification，请完成验证")
    print()
    print("步骤5: 保持浏览器打开")
    print("  不要关闭浏览器")
    print()
    print("步骤6: 运行此脚本")
    print("  python manual_chatglm.py")
    print()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'guide':
        show_setup_guide()
    else:
        # 测试分析
        result = manual_analysis('2026-05-20', '科技', 'AI')
        if result:
            print("结果预览:")
            print(result[:500] + "...")
        else:
            print("分析失败")
