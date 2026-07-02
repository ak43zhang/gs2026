"""DeepSeek 浏览器会话管理

封装浏览器启动、代理选择、登录、发送query、获取回复的完整流程。
主业务文件只需：
    with DeepSeekSession(headless=True) as session:
        session.open(username, password)
        result = session.send_query(query)
"""
import random
import re
import time
from pathlib import Path
from typing import Optional, List

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright, Error

from gs2026.utils import log_util, config_util, display_config, string_util, string_enum
from gs2026.utils.decorators_util import db_retry
from gs2026.analysis.worker.message.deepseek.browser.anti_block import (
    FingerprintRandomizer, BehaviorMime, HumanTypist, DelayBox
)
from gs2026.analysis.worker.message.deepseek.proxy.pool import get_pool
from gs2026.analysis.worker.message.deepseek.proxy.usage_logger import usage_logger
from sqlalchemy.exc import OperationalError
from json.decoder import JSONDecodeError

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 代理模式
PROXY_MODE: str = config_util.get_config("common.deepseek_proxy_mode") or "direct"

# Firefox 浏览器路径
BROWSER_PATH: str = string_enum.FIREFOX_PATH_1509

# 页面超时（毫秒）
PAGE_TIMEOUT: int = 900000


class DeepSeekSession:
    """DeepSeek 浏览器会话，封装代理/直连/登录/发送/关闭的完整生命周期"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser = None
        self._page = None
        self._pw_ctx = None
        self._p = None
        self._proxy_url: Optional[str] = None
        self._username: str = ''
        self._closed = False

    def open(self, username: str, password: str) -> None:
        """启动浏览器 → 处理代理 → 登录 → 等待主界面就绪

        Args:
            username: DeepSeek 账号
            password: DeepSeek 密码
        """
        self._username = username

        # Playwright 初始化（带重试）
        for attempt in range(3):
            try:
                self._pw_ctx = sync_playwright()
                self._p = self._pw_ctx.__enter__()
                break
            except AttributeError as e:
                if attempt == 2:
                    raise RuntimeError(f"Playwright 初始化连续失败3次: {e}") from e
                logger.warning(f"[DeepSeek] Playwright 初始化失败(尝试{attempt+1}/3): {e}")
                time.sleep(2)

        # 启动浏览器
        self._browser, self._page, self._proxy_url = self._launch_browser(username)

        # 防封：到达后随机停顿
        BehaviorMime.idle_look(self._page)
        DelayBox.short()

        # 登录
        self._login(username, password)

        # 启用深度思考/联网搜索/专家模式
        self._enable_features()

    def send_query(self, query: str) -> str:
        """发送 prompt 并等待 AI 回复

        Args:
            query: 分析 prompt 文本

        Returns:
            AI 回复的文本内容（通常为 JSON），失败返回 '{}'
        """
        page = self._page

        # 填入 prompt 并提交
        page.get_by_placeholder("Message DeepSeek").fill(query)
        BehaviorMime.think_pause()
        page.click("._52c986b > div:nth-child(1)")

        time.sleep(random.randint(1, 2))

        # 防封：等待时随便翻翻
        BehaviorMime.casual_scroll(page)

        # 轮询等待回复完成
        CONTINUE_SELECTOR = '.ds-button--outlinedNeutral > span:nth-child(3)'
        RESPONSE_SELECTOR = '._965abe9 > div:nth-child(1) > div:nth-child(1)'
        POLL_INTERVAL = 10000

        elapsed_ms = 0
        while elapsed_ms < PAGE_TIMEOUT:
            try:
                page.wait_for_selector(RESPONSE_SELECTOR, timeout=POLL_INTERVAL)
            except Exception:
                elapsed_ms += POLL_INTERVAL
                continue

            time.sleep(2)
            continue_btn = page.query_selector(CONTINUE_SELECTOR)
            if continue_btn:
                continue_btn.click()
                logger.info("[DeepSeek] 检测到Continue，继续生成")
                time.sleep(3)
                elapsed_ms += 5000
                continue

            break
        else:
            raise TimeoutError(f"[DeepSeek] 等待响应超时({PAGE_TIMEOUT}ms)")

        # 获取回复内容
        response_selectors: List[str] = [
            '.md-code-block > pre:nth-child(2)',
            'div.ds-markdown:nth-child(2) > p:nth-child(1)',
            '.ds-assistant-message-main-content > p:nth-child(1)'
        ]
        result: str = '{}'
        try:
            responses_text: str = '{}'
            for selector in response_selectors:
                responses = page.query_selector(selector)
                if responses is not None:
                    responses_text = responses.inner_text()
                    break
            result = string_util.remove_citation(responses_text).replace("'", "(").replace("\u2019", "）").replace("\u2018", "")
        except AttributeError as e:
            logger.error(f"解析回复时发生属性错误: {e}")

        time.sleep(random.randint(1, 3))
        return result

    def close(self, success: bool = True) -> None:
        """关闭浏览器，报告代理使用结果"""
        if self._closed:
            return
        self._closed = True

        # 代理反馈
        if self._proxy_url:
            if success:
                get_pool().report_success(self._proxy_url, service='deepseek')
                usage_logger.log(service='deepseek', proxy_url=self._proxy_url,
                                account=self._username, result='success')
            else:
                get_pool().report_fail(self._proxy_url)
                usage_logger.log(service='deepseek', proxy_url=self._proxy_url,
                                account=self._username, result='fail')

        # 关闭浏览器
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass

        # 关闭 Playwright 上下文
        if self._pw_ctx:
            try:
                self._pw_ctx.__exit__(None, None, None)
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close(success=(exc_type is None))
        return False

    # ===== 内部方法 =====

    def _launch_browser(self, username: str):
        """根据 PROXY_MODE 启动浏览器"""
        browser = None
        page = None
        proxy_url = None

        if PROXY_MODE == "direct":
            logger.info("[DeepSeek] 直连模式启动浏览器")
            browser = self._p.firefox.launch(headless=self.headless, executable_path=BROWSER_PATH)
            page = display_config.set_page_display_options_chrome(browser)
            FingerprintRandomizer.randomize(page.context)
            page.goto('https://chat.deepseek.com/', timeout=20000)
        else:
            # 代理模式
            pool_ready = get_pool().wait_ready(min_count=10, timeout=180)
            if not pool_ready:
                raise Exception("代理池未就绪，无可用代理")

            for attempt in range(3):
                proxy_url = get_pool().get_proxy(service='deepseek')
                if not proxy_url:
                    if attempt == 2:
                        raise Exception("代理池耗尽，无可用代理")
                    time.sleep(5)
                    continue

                logger.info(f"[DeepSeek] 尝试代理({attempt+1}/3): {proxy_url}")
                browser = self._p.firefox.launch(
                    headless=self.headless,
                    executable_path=BROWSER_PATH,
                    proxy={"server": proxy_url}
                )
                page = display_config.set_page_display_options_chrome(browser)
                FingerprintRandomizer.randomize(page.context)

                try:
                    page.goto('https://chat.deepseek.com/', timeout=20000)
                    if 'deepseek' in page.content().lower():
                        get_pool().report_success(proxy_url)
                        break
                    else:
                        get_pool().report_fail(proxy_url)
                        browser.close()
                        browser = None
                        page = None
                        if attempt == 2:
                            raise Exception("3次代理预验证均失败")
                        time.sleep(2)
                except Exception as e:
                    get_pool().report_fail(proxy_url)
                    if browser:
                        browser.close()
                        browser = None
                        page = None
                    if attempt == 2:
                        raise Exception(f"3次代理预验证均失败: {e}")
                    time.sleep(2)

            if page is None:
                raise Exception("代理预验证后page为None")

        return browser, page, proxy_url

    def _login(self, username: str, password: str) -> None:
        """执行 DeepSeek 登录流程"""
        page = self._page

        page.get_by_role("button").nth(2).click()
        DelayBox.short()

        # 账号输入
        phone_input = page.get_by_placeholder("Phone number / email address")
        phone_input.click()
        BehaviorMime.idle_look(page)
        HumanTypist.type_short(page, 'input[placeholder="Phone number / email address"]', username)
        DelayBox.short()

        # 密码输入
        pwd_input = page.get_by_placeholder("Password")
        pwd_input.click()
        BehaviorMime.idle_look(page)
        HumanTypist.type_short(page, 'input[placeholder="Password"]', password)
        DelayBox.short()

        # 点击登录
        page.get_by_role("button", name="Log in").click()
        BehaviorMime.think_pause()

        # ═══════════════════════════════════════════════════
        # 检测封禁信号
        # ═══════════════════════════════════════════════════
        time.sleep(3)  # 等待页面稳定
        
        try:
            from gs2026.tools.deepseek_ban_checker import check_ban_in_text
            
            page_text = page.inner_text('body')
            ban_signal = check_ban_in_text(page_text)
            
            if ban_signal:
                logger.error(f"[DeepSeek] 检测到封禁信号: {ban_signal}")
                
                # 标记账号禁用
                try:
                    from gs2026.utils.account_pool_util import DistributedAccountPool
                    pool = DistributedAccountPool()
                    pool.deactivate_account(username, service_type='deepseek')
                    logger.warning(f"[DeepSeek] 已禁用封禁账号: {username}")
                except Exception as e:
                    logger.warning(f"[DeepSeek] 标记账号禁用失败: {e}")
                
                raise Exception(f"账号被封禁: {ban_signal}")
                
        except Exception as e:
            if "账号被封禁" in str(e):
                raise  # 向上传递封禁异常
            # 其他检测异常忽略，继续原有流程

        # 等待主界面
        try:
            page.wait_for_selector('[placeholder="Message DeepSeek"]', timeout=15000)
            logger.info("[DeepSeek] 主界面加载完成")
        except Exception:
            logger.warning("[DeepSeek] 等待输入框超时，继续尝试")

    def _enable_features(self) -> None:
        """启用深度思考/联网搜索/专家模式"""
        page = self._page

        # self._ensure_toggle_on(page, r"深度思考|DeepThink|R1", "深度思考")
        # BehaviorMime.idle_look(page)
        # self._ensure_toggle_on(page, r"联网搜索|Search|搜索|联网", "联网搜索")
        # BehaviorMime.idle_look(page)
        self._ensure_expert_mode(page)
        DelayBox.short()

    @staticmethod
    def _ensure_toggle_on(page, name_pattern: str, label: str) -> bool:
        """确保 toggle 按钮开启"""
        try:
            btn = page.get_by_role("button", name=re.compile(name_pattern, re.IGNORECASE))
            btn.wait_for(timeout=5000)
        except Exception:
            logger.warning(f"[DeepSeek] {label} 按钮未找到")
            return False

        is_active = False
        try:
            cls = (btn.get_attribute("class") or "").lower()
            aria = btn.get_attribute("aria-pressed") or ""
            data_active = btn.get_attribute("data-active") or ""
            data_state = btn.get_attribute("data-state") or ""
            is_active = (
                "active" in cls or "selected" in cls or
                "pressed" in cls or "_on" in cls or
                aria == "true" or
                data_active == "true" or
                data_state == "on" or data_state == "active"
            )
        except Exception:
            pass

        if is_active:
            logger.info(f"[DeepSeek] {label} 已启用")
        else:
            btn.click()
            logger.info(f"[DeepSeek] {label} 已点击开启")
            DelayBox.short()
        return True

    @staticmethod
    def _ensure_expert_mode(page) -> bool:
        """确保专家模式已启用"""
        try:
            expert_item = page.locator('[data-model-type="expert"][role="radio"]')
            if expert_item.count() == 0:
                logger.warning("[DeepSeek] 专家模式选项未找到")
                return False

            item = expert_item.first
            aria_checked = item.get_attribute("aria-checked") or "false"
            cls = (item.get_attribute("class") or "").lower()

            if aria_checked == "true" or "selected" in cls:
                logger.info("[DeepSeek] 专家模式已选中")
                return True

            item.click()
            logger.info("[DeepSeek] 专家模式已点击启用")
            DelayBox.short()
            return True
        except Exception as e:
            logger.warning(f"[DeepSeek] 专家模式操作失败: {e}")
            return False
