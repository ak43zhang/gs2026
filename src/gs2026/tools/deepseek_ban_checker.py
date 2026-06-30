"""DeepSeek 账号封禁检测工具

遍历所有 is_active=1 的 DeepSeek 账号，逐个尝试登录，
检测是否被封禁/临时停用，将封禁账号的 is_active 设置为 0。

使用方式：
    python -m gs2026.tools.deepseek_ban_checker

或在代码中调用：
    from gs2026.tools.deepseek_ban_checker import check_all_accounts
    check_all_accounts()
"""

import time
import random
from pathlib import Path
from typing import List, Dict

from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine, text

from gs2026.utils import config_util, log_util, string_enum
from gs2026.analysis.worker.message.deepseek.browser.anti_block import (
    FingerprintRandomizer, DelayBox
)

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 数据库配置
url: str = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# Firefox 浏览器路径
BROWSER_PATH: str = string_enum.FIREFOX_PATH_1509

# 封禁信号关键词
BAN_SIGNALS = [
    '账号已被临时停用', '账号已被停用', '你的账号已被',
    '临时停用', '请完成验证', '账号异常', '账号被封',
    'account has been suspended', 'temporarily suspended',
    'account is restricted', 'unusual activity',
    'suspended', 'banned', 'disabled',
]

# 登录失败信号（密码错误等，不算封禁）
LOGIN_FAIL_SIGNALS = [
    'incorrect password', '密码错误', 'invalid credentials',
    'account not found', '账号不存在',
]


def _get_active_accounts() -> List[Dict]:
    """获取所有活跃的 DeepSeek 账号"""
    with engine.connect() as conn:
        sql = text("SELECT id, username, password FROM accounts WHERE service_type='deepseek' AND is_active=1")
        result = conn.execute(sql)
        return [{"id": row[0], "username": row[1], "password": row[2]} for row in result]


def _mark_banned(account_id: int, username: str, reason: str):
    """将账号标记为 is_active=0"""
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE accounts SET is_active=0 WHERE id=:id"
        ), {"id": account_id})
    logger.warning(f"[封禁检测] ❌ 已禁用账号 id={account_id} username={username} 原因: {reason}")


def _check_single_account(username: str, password: str, headless: bool = True) -> str:
    """检测单个账号是否被封禁

    Returns:
        'ok': 账号正常
        'banned': 账号被封禁
        'login_fail': 登录失败（密码错误等）
        'error': 检测过程异常
    """
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=headless, executable_path=BROWSER_PATH)
            context = browser.new_context()
            FingerprintRandomizer.randomize(context)
            page = context.new_page()

            # 访问 DeepSeek
            page.goto('https://chat.deepseek.com/', timeout=20000)
            time.sleep(2)

            # 检测页面是否已有封禁提示
            page_content = page.content().lower()
            for signal in BAN_SIGNALS:
                if signal.lower() in page_content:
                    browser.close()
                    return 'banned'

            # 点击登录按钮
            try:
                page.get_by_role("button").nth(2).click()
                time.sleep(1)
            except Exception:
                # 可能已经在登录页
                pass

            # 输入账号
            try:
                phone_input = page.get_by_placeholder("Phone number / email address")
                phone_input.fill(username)
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"[封禁检测] 找不到账号输入框: {e}")
                browser.close()
                return 'error'

            # 输入密码
            try:
                pwd_input = page.get_by_placeholder("Password")
                pwd_input.fill(password)
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"[封禁检测] 找不到密码输入框: {e}")
                browser.close()
                return 'error'

            # 点击登录
            try:
                page.get_by_role("button", name="Log in").click()
                time.sleep(8)  # 等待登录响应（增加到8秒）
            except Exception as e:
                logger.warning(f"[封禁检测] 登录按钮点击失败: {e}")
                browser.close()
                return 'error'

            # 检测登录后的页面内容
            page_content = page.content()
            page_text = page.inner_text('body') if page.query_selector('body') else ''

            # 检测封禁信号（只有明确看到封禁文案才判定为banned）
            for signal in BAN_SIGNALS:
                if signal in page_content or signal in page_text:
                    browser.close()
                    return 'banned'

            # 检测登录失败信号
            for signal in LOGIN_FAIL_SIGNALS:
                if signal.lower() in page_content.lower() or signal.lower() in page_text.lower():
                    browser.close()
                    return 'login_fail'

            # 检测是否成功进入主界面（多种选择器，增加容错）
            SUCCESS_SELECTORS = [
                '[placeholder="Message DeepSeek"]',
                '[placeholder="给 DeepSeek 发送消息"]',
                'textarea',
                '.ds-chat-input',
                '[data-testid="chat-input"]',
            ]
            for selector in SUCCESS_SELECTORS:
                try:
                    page.wait_for_selector(selector, timeout=5000)
                    browser.close()
                    return 'ok'
                except Exception:
                    continue

            # 再等一轮（总共约20秒），用更宽泛的方式判断
            time.sleep(5)
            page_url = page.url
            page_text_final = page.inner_text('body') if page.query_selector('body') else ''

            # 再次检查封禁信号
            for signal in BAN_SIGNALS:
                if signal in page_text_final:
                    browser.close()
                    return 'banned'

            # 如果URL包含chat，说明登录成功了
            if 'chat' in page_url:
                browser.close()
                return 'ok'

            # 兜底：未明确检测到封禁信号，标记为uncertain（不自动禁用）
            logger.warning(f"[封禁检测] 未能确认状态，URL={page_url}")
            browser.close()
            return 'uncertain'

    except Exception as e:
        logger.error(f"[封禁检测] 检测异常 {username}: {e}")
        return 'error'


def check_all_accounts(headless: bool = True):
    """遍历所有活跃 DeepSeek 账号，检测封禁状态

    Args:
        headless: 是否无头模式运行浏览器
    """
    accounts = _get_active_accounts()
    total = len(accounts)
    logger.info(f"[封禁检测] 开始检测，共 {total} 个活跃账号")

    results = {"ok": 0, "banned": 0, "login_fail": 0, "error": 0, "uncertain": 0}

    for idx, account in enumerate(accounts, 1):
        account_id = account["id"]
        username = account["username"]
        password = account["password"]

        logger.info(f"[封禁检测] ({idx}/{total}) 检测: {username}")

        status = _check_single_account(username, password, headless)
        results[status] += 1

        if status == 'banned':
            _mark_banned(account_id, username, "登录检测到封禁信号")
        elif status == 'login_fail':
            logger.warning(f"[封禁检测] ⚠️ 登录失败（密码错误?）: {username}")
        elif status == 'ok':
            logger.info(f"[封禁检测] ✅ 账号正常: {username}")
        elif status == 'uncertain':
            logger.warning(f"[封禁检测] ❓ 状态不确定（未检测到封禁信号，但未进入主界面）: {username}")
        else:
            logger.warning(f"[封禁检测] ⚠️ 检测异常: {username}")

        # 每个账号间隔 5-15 秒，避免触发风控
        if idx < total:
            wait = random.randint(5, 15)
            logger.info(f"[封禁检测] 等待 {wait}s 后检测下一个")
            time.sleep(wait)

    # 汇总报告
    logger.info("=" * 50)
    logger.info(f"[封禁检测] 检测完成！")
    logger.info(f"  ✅ 正常: {results['ok']}")
    logger.info(f"  ❌ 封禁（已禁用）: {results['banned']}")
    logger.info(f"  ❓ 不确定（未禁用）: {results['uncertain']}")
    logger.info(f"  ⚠️ 登录失败: {results['login_fail']}")
    logger.info(f"  💥 异常: {results['error']}")
    logger.info("=" * 50)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='DeepSeek 账号封禁检测工具')
    parser.add_argument('--show', action='store_true', help='显示浏览器（非无头模式）')
    args = parser.parse_args()

    check_all_accounts(headless=not args.show)
