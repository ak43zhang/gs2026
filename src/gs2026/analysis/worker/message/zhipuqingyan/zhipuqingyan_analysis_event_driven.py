"""事件驱动分析——智谱清言版本.

本模块实现基于智谱清言大语言模型的事件驱动分析流程，核心功能包括：
    1. 构造多维度评分 prompt（重要程度、业务影响、综合评分等）
    2. 通过 Playwright 自动化操作智谱清言网页端获取 AI 分析结果
    3. 解析返回的 JSON 数据并持久化到 MySQL
    4. 使用 Redis 分布式锁实现多进程任务调度，避免重复分析
    5. 定时检查与轮询机制，支持批量日期分析

依赖:
    - Playwright (Firefox): 浏览器自动化与智谱清言网页交互
    - Redis: 分布式锁，防止并发重复处理
    - SQLAlchemy + MySQL: 数据持久化
    - pandas: SQL 查询结果处理
    - gs2026.utils: 配置、日志、邮件、字符串处理等工具集

Typical usage::

    from gs2026.analysis.worker.message.zhipuqingyan.zhipuqingyan_analysis_event_driven import analysis_event_driven
    analysis_event_driven(['2026-03-20', '2026-03-21'])
"""

import os
import random
import re
import time
import warnings
from datetime import datetime
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Callable, Any, List, Tuple, Optional

import pandas as pd
import redis
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright, Error
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, SAWarning

from gs2026.utils import mysql_util, config_util, email_util, display_config, pandas_display_config
from gs2026.utils import log_util, string_enum, string_util
from gs2026.utils.decorators_util import db_retry
from gs2026.utils.task_runner import run_daemon_task
from gs2026.analysis.worker.message.zhipuqingyan.result_processor import process_domain

# 忽略 SQLAlchemy 的 SAWarning，避免日志噪音
warnings.filterwarnings("ignore", category=SAWarning)

# ===== 模块级初始化 =====

# 日志器，以当前文件绝对路径作为 logger 名称
logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 设置 pandas 全局显示选项（列宽、行数等）
pandas_display_config.set_pandas_display_options()

# 从配置文件读取数据库连接 URL 和 Redis 连接信息
url: str = config_util.get_config("common.url")
redis_host: str = config_util.get_config('common.redis.host')
redis_port: int = config_util.get_int('common.redis.port')

# 创建 SQLAlchemy 引擎，启用连接池回收和预检测
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 浏览器可执行文件路径（支持 Firefox 和 Edge）
browser_type: str = config_util.get_config('common.browser_type', 'edge')  # 'firefox' 或 'edge'
if browser_type.lower() == 'edge':
    browser_path: str = config_util.get_config('common.edge_path', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
else:
    browser_path: str = string_enum.FIREFOX_PATH_1509

# MySQL 工具类实例
mysql_tool = mysql_util.get_mysql_tool(url)

# 邮件工具类实例（用于异常告警）
email_util = email_util.EmailUtil()

# Playwright 页面超时时间（毫秒），15 分钟
page_timeout: int = 900000

# Redis 客户端，用于分布式锁
redis_client: redis.Redis = redis.Redis(
    host=redis_host,
    port=redis_port,
    decode_responses=True
)

# Cookies 存储路径
cookies_dir = Path(__file__).parent / 'cookies'
cookies_dir.mkdir(exist_ok=True)
cookies_file = cookies_dir / 'chatglm_cookies.json'


class ChatGLMBrowser:
    """智谱清言浏览器操作类（支持 Cookies 持久化）"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.page = None
        self.playwright = None
        self.context = None
    
    def _random_delay(self, min_sec: float = 0.5, max_sec: float = 2.0):
        """随机延迟，模拟真人思考时间"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
    
    def _random_mouse_move(self):
        """随机鼠标移动"""
        try:
            if self.page:
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                self.page.mouse.move(x, y)
                self._random_delay(0.1, 0.3)
        except:
            pass
    
    def _random_scroll(self):
        """随机滚动"""
        try:
            if self.page:
                scroll_y = random.randint(-100, 100)
                self.page.evaluate(f'window.scrollBy(0, {scroll_y})')
                self._random_delay(0.2, 0.5)
        except:
            pass
    
    def _simulate_human_behavior(self):
        """模拟真人行为：随机移动鼠标、滚动"""
        if random.random() < 0.3:
            self._random_mouse_move()
        if random.random() < 0.2:
            self._random_scroll()
        
    def _load_cookies(self) -> list:
        """从文件加载 cookies"""
        try:
            if cookies_file.exists():
                with open(cookies_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    logger.info(f"已加载 {len(cookies)} 个 cookies")
                    return cookies
        except Exception as e:
            logger.warning(f"加载 cookies 失败: {e}")
        return []
    
    def _save_cookies(self) -> None:
        """保存 cookies 到文件"""
        try:
            if self.context:
                cookies = self.context.cookies()
                with open(cookies_file, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                logger.info(f"已保存 {len(cookies)} 个 cookies")
        except Exception as e:
            logger.warning(f"保存 cookies 失败: {e}")
        
    def launch(self) -> None:
        """启动浏览器（支持 Firefox/Edge 和 cookies 复用）"""
        self.playwright = sync_playwright().start()
        
        # 添加随机延迟，模拟人工操作
        time.sleep(random.uniform(1, 3))
        
        # 根据浏览器类型启动
        if browser_type.lower() == 'edge':
            logger.info(f"使用 Edge 浏览器: {browser_path}")
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                executable_path=browser_path,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.0 Edg/125.0.0.0'
        else:
            logger.info(f"使用 Firefox 浏览器: {browser_path}")
            self.browser = self.playwright.firefox.launch(
                headless=self.headless, 
                executable_path=browser_path,
                args=['--disable-blink-features=AutomationControlled']
            )
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0'

        # 加载已保存的 cookies
        saved_cookies = self._load_cookies()
        
        # 创建新上下文，添加反爬虫配置
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=user_agent,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        
        # 添加已保存的 cookies
        if saved_cookies:
            try:
                self.context.add_cookies(saved_cookies)
                logger.info("已添加保存的 cookies")
            except Exception as e:
                logger.warning(f"添加 cookies 失败: {e}")
        
        self.page = self.context.new_page()
        
        # 注入脚本隐藏自动化特征
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)
        
        logger.info("浏览器启动成功")

        
    def navigate(self) -> None:
        """访问智谱清言页面"""
        self.page.goto('https://chatglm.cn/main', timeout=page_timeout)
        logger.info("页面加载完成")

        # 检查并处理 Access Verification 验证页面
        # self._handle_verification()
        
    def _handle_verification(self) -> None:
        """处理 Access Verification 验证页面"""
        try:
            # 检查页面标题或内容是否包含验证关键词
            page_title = self.page.title()
            page_content = self.page.content()
            
            verification_keywords = ['Access Verification', '验证', 'Verification', '安全检查', '安全验证']
            is_verification_page = any(keyword in page_title or keyword in page_content 
                                      for keyword in verification_keywords)
            
            if is_verification_page:
                logger.warning("检测到验证页面，等待人工处理或自动跳过...")
                
                # 等待一段时间，看是否能自动通过
                time.sleep(5)
                
                # 尝试刷新页面
                self.page.reload(timeout=page_timeout)
                logger.info("页面已刷新")
                
                # 再次检查
                page_content = self.page.content()
                if any(keyword in page_content for keyword in verification_keywords):
                    logger.error("验证页面仍然存在，可能需要人工处理")
                    raise Exception("Access Verification 验证未通过")
                else:
                    logger.info("验证已通过")
            
        except Exception as e:
            logger.error(f"处理验证页面失败: {e}")
            raise
        
    def close_popup(self, is_second=False) -> None:
        """关闭产品推广弹窗
        
        Args:
            is_second: 是否为第二次弹窗（新对话后的弹窗）
        """
        try:
            # 如果是第二次弹窗，使用特定选择器
            if is_second:
                try:
                    # 用户提供的特定选择器
                    self.page.click('#maasGuidePopover svg', timeout=3000)
                    logger.info("关闭第二次弹窗: #maasGuidePopover")
                    time.sleep(random.uniform(0.5, 1))
                    return
                except:
                    pass
            
            # 尝试多种方式关闭弹窗
            # 1. 点击"我知道了"按钮
            try:
                self.page.click('button:has-text("我知道了")', timeout=3000)
                logger.info("关闭弹窗: 我知道了")
                return
            except:
                pass
                
            # 2. 点击关闭按钮
            try:
                self.page.click('button[class*="close"], [class*="close"] button', timeout=3000)
                logger.info("关闭弹窗: 关闭按钮")
                return
            except:
                pass
                
            # 3. 按 ESC 键
            self.page.press('body', 'Escape')
            logger.info("关闭弹窗: ESC键")
            
        except Exception as e:
            logger.warning(f"关闭弹窗失败或无需关闭: {e}")
    
    def close_second_popup(self) -> None:
        """专门关闭第二次弹窗（新对话后）"""
        try:
            logger.info("关闭第二次弹窗...")
            
            # 使用用户提供的特定选择器
            selectors = [
                '#maasGuidePopover svg',
                '#maasGuidePopover .close-btn-container svg',
                '#maasGuidePopover > div > div.close-btn-container > svg',
                '[id*="maasGuide"] svg',
                '.close-btn-container svg',
            ]
            
            for selector in selectors:
                try:
                    self.page.click(selector, timeout=3000)
                    logger.info(f"关闭第二次弹窗: {selector}")
                    time.sleep(random.uniform(0.5, 1))
                    return
                except:
                    continue
            
            # 如果特定选择器都失败，使用通用方法
            self.close_popup()
            
        except Exception as e:
            logger.warning(f"关闭第二次弹窗失败: {e}")
    
    def start_new_chat(self) -> None:
        """点击新对话按钮，创建新的对话"""
        try:
            logger.info("准备创建新对话...")
            
            # 模拟真人行为
            self._simulate_human_behavior()
            self._random_delay(0.5, 1.5)
            
            # 使用用户提供的选择器
            try:
                # 先滚动到可见
                self.page.locator('div.new-session').scroll_into_view_if_needed(timeout=3000)
                self._random_delay(0.3, 0.6)
                
                # 随机鼠标移动
                self._random_mouse_move()
                
                # 点击
                self.page.click('div.new-session', timeout=5000)
                logger.info("已点击新对话按钮 (div.new-session)")
                time.sleep(random.uniform(3, 5))
                return
            except:
                pass
            
            # 备选选择器
            selectors = [
                'div.aside-subjects > div.new-session',
                '[class*="new-session"]',
                'button:has-text("新对话")',
                'div:has-text("新对话")',
                'aside div.new-session',
                'section > aside div.new-session',
            ]
            
            for selector in selectors:
                try:
                    # 滚动到可见
                    self.page.locator(selector).scroll_into_view_if_needed(timeout=2000)
                    self._random_delay(0.3, 0.6)
                    
                    self.page.click(selector, timeout=3000)
                    logger.info(f"已点击新对话按钮 ({selector})")
                    time.sleep(random.uniform(3, 5))
                    return
                except:
                    continue
            
            # 尝试 XPath
            try:
                element = self.page.locator('xpath=//div[contains(@class, "new-session")]')
                element.scroll_into_view_if_needed(timeout=2000)
                self._random_delay(0.3, 0.6)
                element.click(timeout=3000)
                logger.info("已点击新对话按钮 (XPath)")
                time.sleep(random.uniform(3, 5))
                return
            except:
                pass
            
            # 如果都没找到，尝试键盘快捷键
            try:
                self.page.keyboard.press('Control+n')
                logger.info("使用快捷键 Ctrl+N 创建新对话")
                time.sleep(random.uniform(3, 5))
                return
            except:
                pass
                
            logger.warning("未找到新对话按钮，可能已在对话中")
            
        except Exception as e:
            logger.warning(f"点击新对话失败: {e}")
            
    def enable_thinking(self) -> None:
        """启用思考模式（深度思考）"""
        try:
            logger.info("准备启用思考模式...")
            
            # 模拟真人行为
            self._simulate_human_behavior()
            self._random_delay(0.5, 1)
            
            # 尝试多种精确选择器
            selectors = [
                'button:has-text("思考")',
                'div:has-text("思考"):has(> svg)',
                '[class*="thinking"]',
                '[class*="deep-think"]',
                '[data-testid*="thinking"]',
                'button:has-text("思考") >> nth=0',
            ]
            
            for selector in selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.click(selector, timeout=3000)
                        logger.info(f"启用思考模式 ({selector})")
                        time.sleep(random.uniform(1.5, 2.5))
                        return
                except:
                    continue
            
            # 备选：使用 first
            try:
                self.page.get_by_text('思考', exact=False).first.click()
                logger.info("启用思考模式 (first)")
                time.sleep(random.uniform(1.5, 2.5))
                return
            except:
                pass
            
            logger.warning("未找到思考按钮，可能已启用或页面结构变化")
            
        except Exception as e:
            logger.error(f"启用思考模式失败: {e}")
            raise
            
    def enable_web_search(self) -> None:
        """启用联网搜索功能"""
        try:
            logger.info("准备启用联网搜索...")
            
            # 随机延迟
            self._random_delay(0.5, 1)
            
            # 使用用户提供的特定选择器
            try:
                selector = '#search-input-box .session-button-container > div:nth-child(2) > span'
                self.page.click(selector, timeout=5000)
                logger.info(f"启用联网搜索 ({selector})")
                time.sleep(random.uniform(1.5, 2.5))
                return
            except:
                pass
            
            # 备选选择器
            selectors = [
                '#search-input-box span:has-text("联网")',
                '.session-button-container > div:nth-child(2)',
                'button:has-text("联网")',
                'div:has-text("联网"):has(> svg)',
                '[class*="web-search"]',
                'button:has-text("联网") >> nth=0',
            ]
            
            for selector in selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.click(selector, timeout=3000)
                        logger.info(f"启用联网搜索 ({selector})")
                        time.sleep(random.uniform(1.5, 2.5))
                        return
                except:
                    continue
            
            # 如果都失败，尝试 get_by_text 但使用 first
            try:
                self.page.get_by_text('联网', exact=False).first.click()
                logger.info("启用联网搜索 (first)")
                time.sleep(random.uniform(1.5, 2.5))
                return
            except:
                pass
            
            logger.warning("未找到联网按钮，可能已启用或页面结构变化")
            
        except Exception as e:
            logger.error(f"启用联网搜索失败: {e}")
            raise
            
    def check_and_close_login_popup(self) -> bool:
        """检查并关闭登录弹窗"""
        try:
            # 检查是否出现登录界面
            page_content = self.page.content()
            login_keywords = ['登录', '手机号登录', '微信登录', '短信验证码']
            
            is_login_popup = any(keyword in page_content for keyword in login_keywords)
            
            if is_login_popup:
                logger.warning("检测到登录弹窗，尝试关闭...")
                
                # 尝试关闭登录弹窗
                close_selectors = [
                    '[class*="close"]',
                    'button[class*="close"]',
                    '.login-popup .close',
                    '.modal-close',
                    'svg[class*="close"]',
                ]
                
                for selector in close_selectors:
                    try:
                        self.page.click(selector, timeout=2000)
                        logger.info(f"已关闭登录弹窗 ({selector})")
                        time.sleep(random.uniform(1, 2))
                        return True
                    except:
                        continue
                
                # 尝试 ESC 键
                try:
                    self.page.press('body', 'Escape')
                    logger.info("已关闭登录弹窗 (ESC)")
                    time.sleep(random.uniform(1, 2))
                    return True
                except:
                    pass
                
                logger.warning("未能关闭登录弹窗")
                return False
            
            return True  # 没有登录弹窗
            
        except Exception as e:
            logger.warning(f"检查登录弹窗失败: {e}")
            return True
    
    def send_message(self, query: str) -> None:
        """发送消息（一次性粘贴，处理登录弹窗）"""
        try:
            logger.info(f"准备发送消息（{len(query)} 字符）...")
            
            # 1. 找到输入框
            textarea_selector = '#search-input-box textarea'
            textarea = self.page.locator(textarea_selector)
            
            # 点击输入框获取焦点
            textarea.click()
            self._random_delay(0.3, 0.8)
            
            # 2. 一次性填入消息（fill方式）
            logger.info("正在填入消息...")
            try:
                textarea.fill(query)
                logger.info("消息已填入")
            except Exception as e:
                logger.warning(f"fill失败，使用evaluate: {e}")
                # 备选：通过 evaluate 设置
                self.page.evaluate(f'''() => {{
                    const textarea = document.querySelector('#search-input-box textarea');
                    if (textarea) {{
                        textarea.value = {json.dumps(query)};
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}''')
                logger.info("消息已通过 evaluate 填入")
            
            # 3. 随机停顿（模拟查看内容）
            self._random_delay(1, 2)
            
            # 4. 点击执行按钮
            logger.info("点击执行按钮...")
            send_selector = '#search-input-box .enter.is-main-chat img'
            
            try:
                self.page.click(send_selector, timeout=5000)
                logger.info("消息已发送")
            except:
                # 备选：回车发送
                textarea.press('Enter')
                logger.info("消息已发送（回车）")
            
            # 5. 检查登录弹窗
            time.sleep(1)
            if not self.check_and_close_login_popup():
                logger.warning("登录弹窗未关闭，重新发送...")
                
                # 重新填入完整 query
                textarea = self.page.locator(textarea_selector)
                textarea.click()
                self._random_delay(0.3, 0.8)
                
                # 清空并重新填入
                textarea.fill('')
                self._random_delay(0.3, 0.5)
                textarea.fill(query)
                self._random_delay(1, 2)
                
                # 再次点击执行
                try:
                    self.page.click(send_selector, timeout=5000)
                    logger.info("消息已重新发送")
                except:
                    textarea.press('Enter')
                    logger.info("消息已重新发送（回车）")
            
            self._random_delay(0.5, 1)
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            raise
            
    def wait_for_response(self, timeout: int = 300) -> str:
        """等待并获取回复（带随机行为模拟）"""
        logger.info(f"等待回复（最长 {timeout} 秒）...")
        
        start_time = time.time()
        last_text = ""
        stable_count = 0
        
        while time.time() - start_time < timeout:
            try:
                # 检查验证页面
                page_content = self.page.content()
                verification_keywords = ['Access Verification', '验证', 'Verification', '安全检查']
                if any(keyword in page_content for keyword in verification_keywords):
                    logger.error("检测到验证页面")
                    raise Exception("Access Verification 验证页面")
                
                # 随机行为模拟
                if random.random() < 0.3:
                    self._random_mouse_move()
                if random.random() < 0.1:
                    self._random_scroll()
                
                # 尝试获取回复
                selectors = [
                    '.markdown-body',
                    '.chat-content',
                    '[class*="message"]',
                    '[class*="response"]',
                    'div[class*="markdown"]'
                ]
                
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
                                        logger.info(f"回复完成，共 {len(text)} 字符")
                                        return text
                                else:
                                    stable_count = 0
                                    last_text = text
                                    logger.debug(f"收到回复... ({len(text)} 字符)")
                    except:
                        continue
                
                self._random_delay(1.5, 2.5)
                
            except Exception as e:
                logger.warning(f"等待出错: {e}")
                self._random_delay(1, 2)
        
        logger.warning("等待超时，返回当前内容")
        return last_text
            
    def close(self) -> None:
        """关闭浏览器（保存 cookies）"""
        try:
            # 保存 cookies
            self._save_cookies()
            
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器失败: {e}")


def build_prompt(t_date: str, main_area: str, child_area: str, 
                 bk_dic_str: str, gn_dic_str: str) -> str:
    """构造智谱清言分析 Prompt
    
    完全复用 DeepSeek 版本的 Prompt 模板
    """
    query = f"{t_date}全球重要大事件集锦，按重要程度给出30条主领域为{main_area}，子领域为{child_area}的消息，" + """
重要程度评分：按照 权威性与级别 角度评估程度分为 国家级政策（5分）、部委/地方政策（4分）、行业会议（3分）、公司公告（2分）、市场传闻（1分）。按照 新颖性与想象力 角度评估程度分为 新技术/新政策（5分）、现有产业数据向好（3分）。按照 相关性与纯度 角度评估程度分为 直接受益（核心业务高度相关）（5分）、间接受益（产业链上下游）（3分）、情绪相关（概念沾边）（1分），最终由三者分数相加，总分范围0至15分。
业务影响维度评分：（每个维度-5至5分，总分范围-60至60）
    从12个关键经营维度评估消息的实质性影响，正面影响为正分，负面影响为负分，无影响为0分。评分时需结合消息内容具体分析。
    按照 成本控制 维度评估程度分为	显著降低成本（5）、一定程度降低成本（3）、略有影响（1）	显著提高成本（-5）、一定程度提高（-3）、略有提高（-1），
    按照 运营效率 维度评估程度分为	大幅提升效率（5）、有所提升（3）、轻微提升（1）	大幅降低效率（-5）、有所降低（-3）、轻微降低（-1），
    按照 资金与财务 维度评估程度分为	极大改善现金流/利润（5）、明显改善（3）、略有改善（1）	极大恶化（-5）、明显恶化（-3）、略有恶化（-1），
    按照 技术或工艺突破 维度评估程度分为	重大突破（5）、明显进步（3）、小幅改进（1）	技术落后（-5）、竞争力下降（-3）、小幅退步（-1），
    按照 产品定价权 维度评估程度分为	显著增强定价能力（5）、有所增强（3）、轻微增强（1）	显著削弱（-5）、有所削弱（-3）、轻微削弱（-1），
    按照 市场份额扩张 维度评估程度分为	大幅提升市占率（5）、明显提升（3）、小幅提升（1）	大幅下降（-5）、明显下降（-3）、小幅下降（-1），
    按照 产业链地位 维度评估程度分为	大幅提升话语权（5）、有所提升（3）、轻微提升（1）	大幅降低（-5）、有所降低（-3）、轻微降低（-1），
    按照 产品结构升级 维度评估程度分为	推动高端化/高附加值（5）、明显优化（3）、小幅调整（1）	导致低端化（-5）、明显劣化（-3）、小幅劣化（-1），
    按照 成功拓展新业务 维度评估程度分为	开辟全新业务领域（5）、进入新市场（3）、尝试新方向（1）	退出核心业务（-5）、收缩业务（-3）、暂停拓展（-1），
    按照 政策支持 维度评估程度分为	获得强力政策扶持（5）、一般性支持（3）、间接利好（1）	遭遇政策打压（-5）、限制（-3）、间接利空（-1），
    按照 行业趋势红利 维度评估程度分为	处于爆发风口（5）、明显受益（3）、略有受益（1）	逆势而行（-5）、明显受损（-3）、略有受损（-1），
    按照 输入成本下降 维度评估程度分为	大幅降低原材料/能源成本（5）、明显降低（3）、小幅降低（1）	大幅上升（-5）、明显上升（-3）、小幅上升（-1），
    最终综合分析算出。
综合评分：（通过重要程度评分×4+业务影响维度评分）。
利空利好（由业务影响维度评分和综合评分分析得出，业务影响维度评分为负则为利空，综合评分小于0则为利空，0-60则为中性，大于60则为利好，字典值有利好、利空、中性三个字典值）。
消息大小（由综合评分计算得出，重大：90 ≤ 综合评分，大：60 ≤ 综合评分 < 90，中：30 ≤ 综合评分 < 60，小：综合评分 < 30,字典值有重大，大，中，小四个）。
涉及板块（板块字典："""+bk_dic_str+"""，以英文逗号分隔）。
涉及概念（概念字典："""+gn_dic_str+"""，以英文逗号分隔）。
股票代码（请根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息直接受益或者受损的a股沪深板块股票代码，多值按照英文逗号分隔，6位代码），
时间（事件发表最早的时间，时间格式为yyyy-MM-dd HH:mm:ss），
事件来源（事件最早时间的来源）
原因分析（该字段主要根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息对a股具体股票代码直接受益或者受损的原因）,
深度分析：(是根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息的实质性影响,深度分析结果按照前面的维度+详细分析原因+维度评估程度分组成)
返回结果为json对象，json 结构为       
{"消息集合": [
    "主领域": "",
    "子领域": "",
    "时间":"",
    "事件来源":"",
    "关键事件": "",
    "简要描述": "",
    "利空利好":"",
    "消息大小":"",
    "涉及板块": "",
    "涉及概念": "",
    "股票代码": "",
    "原因分析":"",
    "重要程度评分":"",
    "业务影响维度评分":"",
    "综合评分":"",
    "深度分析":[""]
]}  
请返回json结果。
"""
    return query


@db_retry(max_retries=30, initial_delay=1, max_delay=60,
          retriable_errors=(OperationalError, PlaywrightTimeoutError, JSONDecodeError, KeyError, Error))
def zhipuqingyan_analysis(query: str, _headless: bool) -> str | None:
    """通过智谱清言获取 AI 分析结果。

    使用 Playwright 自动化操作智谱清言网页端，启用思考和联网功能，
    发送 query 并等待 AI 返回分析结果。

    Args:
        query: 发送给智谱清言的分析 prompt 文本。
        _headless: 是否以无头模式运行浏览器。True 为无头模式。

    Returns:
        智谱清言返回的 AI 分析结果字符串（通常为 JSON 格式）。
        如果获取失败则返回 '{}'。

    Raises:
        OperationalError: 数据库操作失败。
        PlaywrightTimeoutError: 页面加载或元素等待超时。
        JSONDecodeError: JSON 解析异常。
        KeyError: 字段缺失。
        Error: Playwright 通用错误。

    Note:
        该函数使用 @db_retry 装饰器，最多重试 30 次，
        初始延迟 1 秒，最大延迟 60 秒。
    """
    logger.info(f"开始智谱清言分析，query长度: {len(query)}")
    logger.info(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
    
    browser = ChatGLMBrowser(headless=_headless)
    
    try:
        # 简化流程：按人为操作顺序
        # 1. 启动浏览器
        browser.launch()
        
        # 2. 访问页面
        browser.navigate()
        
        # 3. 关闭第一次弹窗（访问页面后）
        browser.close_popup()
        
        # 4. 点击新对话
        browser.start_new_chat()
        
        # 5. 关闭第二次弹窗（新对话后）- 使用特定选择器
        browser.close_second_popup()

        # 6. 启用联网搜索
        browser.enable_web_search()
        
        # 7. 发送消息
        browser.send_message(query)

        time.sleep(10000)
        
        # 7. 等待并获取回复 vc
        result = browser.wait_for_response()
        
        # 8. 清理结果
        result = string_util.remove_citation(result).replace("'", "(").replace("\u2019", "）").replace("'", "")
        
        logger.info(f"智谱清言分析完成，结果长度: {len(result)}")
        return result
        
    except Exception as e:
        logger.error(f"智谱清言分析失败: {e}")
        return '{}'
        
    finally:
        browser.close()


def zhipuqingyan_ai(
    query_list: List[Tuple[str, str, str]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool
) -> None:
    """对指定的领域-日期组合列表执行智谱清言 AI 分析。

    遍历 query_list 中的每条记录，构造分析 prompt 并调用智谱清言
    获取 JSON 格式的分析结果，最后将结果插入到分析结果表中。

    Args:
        query_list: 待分析记录列表，每个元素为 (日期, 主领域, 子领域) 的元组。
        bk_dic_str: 板块字典字符串，以英文逗号分隔的板块名称列表。
        gn_dic_str: 概念字典字符串，以英文逗号分隔的概念名称列表。
        table_name: 源数据表名称，用于日志标识。
        analysis_table_name: 分析结果存储表名称。
        _headless: 是否以无头模式运行浏览器。

    Returns:
        None

    Raises:
        Exception: 当 zhipuqingyan_analysis 调用失败且超过重试次数时抛出。

    Example::

        zhipuqingyan_ai(
            [('2026-03-20', '科技', 'AI')],
            '半导体,新能源',
            'ChatGPT,大模型',
            'news_area',
            'analysis_area_chatglm2026',
            True
        )
    """
    start = time.time()

    for i in query_list:
        t_date: str = i[0]
        main_area: str = i[1]
        child_area: str = i[2]

        # 构造智谱清言分析 prompt
        query = build_prompt(t_date, main_area, child_area, bk_dic_str, gn_dic_str)
        
        # 对 prompt 进行敏感词替换，避免触发平台过滤
        query = string_util.sensitive_word_replacement(query)
        print(query)

        # 调用智谱清言获取 AI 分析结果
        analysis: str = zhipuqingyan_analysis(query, _headless)

        # 清理返回结果中的非 JSON 前缀和注释
        analysis = string_util.remove_json_prefix(analysis, 'json')
        analysis = string_util.remove_json_prefix(analysis, 'Copy')
        analysis = string_util.remove_json_prefix(analysis, 'Code')
        analysis = string_util.remove_json_comments(analysis)
        analysis = analysis.lstrip()

        # 从字符串中提取合法的 JSON 数据
        json_data, remaining_text = string_util.extract_json_from_string(analysis)

        if string_util.is_valid_json(json_data) and json_data != '{}':
            # JSON 合法且非空，插入分析结果到数据库
            update_sql = f"INSERT INTO {analysis_table_name} (news_date,main_area,child_area,json_data) VALUES ('{t_date}','{main_area}','{child_area}','{json_data}')"
            mysql_tool.update_data(update_sql)
            
            # 拆分入库到新表
            try:
                stats = process_domain(json_data, main_area, child_area, t_date, version='zhipuqingyan-1.0.0')
                logger.info(f"领域分析拆分入库: {stats}")
            except Exception as e:
                logger.error(f"领域分析拆分入库失败: {e}")
        else:
            logger.error(table_name + "该数据ai分析失败，请重试")

    end = time.time()
    execution_time: float = end - start
    logger.info(f"{table_name}智谱清言AI分析耗时: {execution_time} 秒")


def area_ai_analysis(
    table_name: str,
    analysis_table_name: str,
    start_date: str,
    _headless: bool
) -> bool | None:
    """从数据库获取待分析记录，使用 Redis 分布式锁进行单条分析。

    查询最多 10 条尚未分析的领域记录作为候选，遍历候选列表
    尝试获取 Redis 分布式锁，成功后调用 zhipuqingyan_ai 进行分析。

    Args:
        table_name: 领域配置源表名称（如 'news_area'）。
        analysis_table_name: 分析结果目标表名称（如 'analysis_area_chatglm2026'）。
        start_date: 目标分析日期，格式为 'YYYY-MM-DD'。
        _headless: 是否以无头模式运行浏览器。

    Returns:
        bool: True 表示仍有待处理任务（需继续轮询），
              False 表示所有任务已完成。

    Raises:
        Exception: 单条记录处理失败时记录日志并继续尝试下一条。
    """
    # 查询尚未分析的候选记录
    sql = f"""
        select SQL_NO_CACHE '{start_date}' as t_date,
               {table_name}.main_area,
               {table_name}.child_area
        from {table_name}
        left join (select * from {analysis_table_name} where news_date='{start_date}') as analysis_area2
            on {table_name}.child_area = analysis_area2.child_area
        where is_use='1' and analysis_area2.news_date is null
        order by rand()
        limit 10
    """
    # 板块字典查询
    bk_dic_sql: str = "select name from data_industry_code_ths"
    # 概念字典查询
    gn_dic_sql: str = "select name from ths_gn_names_rq where flag='1'"

    with engine.connect() as conn:
        candidates: List[dict] = pd.read_sql(sql, con=conn).to_dict('records')
        if not candidates:
            return False

        bk_dic_str: str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str: str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))

    # 遍历候选记录，尝试获取 Redis 分布式锁
    for cand in candidates:
        t_date: str = cand['t_date']
        main_area: str = cand['main_area']
        child_area: str = cand['child_area']

        # 构造分布式锁的 key
        lock_key: str = f"area_ai_lock:zhipuqingyan:{table_name}:{t_date}:{main_area}:{child_area}"
        lock = redis_client.lock(lock_key, timeout=900, blocking_timeout=0)

        if lock.acquire(blocking=False):
            try:
                # 成功获取锁，执行 AI 分析
                zhipuqingyan_ai([(t_date, main_area, child_area)], bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
                return True
            except Exception as e:
                logger.error(f"处理记录 {t_date} {main_area} {child_area} 失败: {e}")
            finally:
                try:
                    lock.release()
                except redis.exceptions.LockNotOwnedError:
                    pass

    return True


def area_ai(area_ai_date: str, polling_time: int) -> None:
    """对指定日期执行领域 AI 分析的轮询循环。

    持续调用 area_ai_analysis 直到所有领域记录分析完毕。
    每次分析完成后休眠 polling_time 秒再进行下一轮。

    Args:
        area_ai_date: 目标分析日期，格式为 'YYYY-MM-DD'。
        polling_time: 每轮分析之间的休眠时间（秒）。

    Returns:
        None
    """
    flag: bool = True
    year: str = area_ai_date[0:4]
    table: str = "news_area"
    analysis_table: str = f"analysis_area{year}"

    while flag:
        flag = area_ai_analysis(table, analysis_table, area_ai_date, False)
        time.sleep(polling_time)


def check_time_and_execute(
        target_date: datetime,
        check_interval: int,
        execute_func: Callable[..., Any],
        *func_args: Any,
        **func_kwargs: Any
) -> Any:
    """定时检查并在目标时间到达后执行指定函数。

    以 check_interval 为间隔循环检查当前时间，当当前时间
    超过 target_date 时执行 execute_func 并返回其结果。

    Args:
        target_date: 目标执行时间。
        check_interval: 检查间隔（秒）。
        execute_func: 需要执行的回调函数。
        *func_args: 传递给 execute_func 的位置参数。
        **func_kwargs: 传递给 execute_func 的关键字参数。

    Returns:
        execute_func 的返回值。
    """
    logger.info(f"目标时间: {target_date.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("开始循环检查，每隔1分钟检查一次...")

    while True:
        current_time: datetime = datetime.now()

        if current_time > target_date:
            logger.info(f"\n✅ 时间已到！当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"开始执行函数: {execute_func.__name__}...")

            result = execute_func(*func_args, **func_kwargs)

            logger.info("任务执行完成，程序继续运行...")
            return result

        else:
            remaining = target_date - current_time
            days: int = remaining.days
            seconds: int = remaining.seconds
            hours: int = seconds // 3600
            minutes: int = (seconds % 3600) // 60

            current_minute: int = current_time.minute
            if current_minute % 10 == 0 or remaining.total_seconds() < 3600:
                logger.info(f"当前时间: {current_time.strftime('%H:%M:%S')}, "
                            f"剩余: {days}天{hours}小时{minutes}分钟")

        time.sleep(check_interval)


def analysis_event_driven(date_list_: List[str]) -> None:
    """事件驱动分析主入口，按日期列表依次执行全领域 AI 分析。

    遍历日期列表，对每个日期调用 area_ai 完成所有领域的分析。
    发生异常时通过邮件发送告警通知。

    Args:
        date_list_: 待分析日期列表，每个元素格式为 'YYYY-MM-DD'。

    Returns:
        None
    """
    for area_date in date_list_:
        logger.info('=============================' + area_date + '=============================')
        area_ai(area_date, 1)


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='智谱清言领域事件分析')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()
    
    date_list = ['2026-05-10']
    
    if args.params:
        try:
            params = json.loads(args.params)
            if 'date_list' in params:
                date_list = params['date_list']
                logger.info(f'从参数获取日期列表: {date_list}')
        except json.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')
    
    run_daemon_task(target=analysis_event_driven, args=(date_list,))
