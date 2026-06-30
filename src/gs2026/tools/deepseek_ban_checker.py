"""DeepSeek 账号封禁检测工具

遍历所有 is_active=1 的 DeepSeek 账号，逐个尝试登录，
检测是否被封禁/临时停用，将封禁账号的 is_active 设置为 0。

使用方式：
    python -m gs2026.tools.deepseek_ban_checker
    python -m gs2026.tools.deepseek_ban_checker --show
    python -m gs2026.tools.deepseek_ban_checker --test DboutvWwwoyz69500@outlook.com

判定原则：宁可漏报（uncertain），不可误禁（banned）
- 只有明确看到封禁文案才判定为 banned
- 只检查页面可见文本，不检查原始HTML
- 未确认状态标记为 uncertain，不自动禁用
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

# ★ 封禁信号关键词（精确短语，不含通用词）
# 只使用完整的封禁提示文案，避免 'disabled'/'suspended' 等通用词匹配HTML属性
BAN_SIGNALS = [
    '账号已被临时停用',
    '账号已被停用',
    '你的账号已被',
    '临时停用',
    '账号异常',
    '账号被封',
    'Your account has been suspended',
    'account has been temporarily suspended',
    'account is restricted',
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


def _get_account_by_username(username: str) -> Dict:
    """按用户名获取单个账号"""
    with engine.connect() as conn:
        sql = text("SELECT id, username, password FROM accounts WHERE username=:u")
        result = conn.execute(sql, {"u": username}).fetchone()
        if result:
            return {"id": result[0], "username": result[1], "password": result[2]}
        return None


def _mark_banned(account_id: int, username: str, reason: str):
    """将账号标记为 is_active=0"""
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE accounts SET is_active=0 WHERE id=:id"
        ), {"id": account_id})
    logger.warning(f"[封禁检测] ❌ 已禁用账号 id={account_id} username={username} 原因: {reason}")


def _check_single_account(username: str, password: str, headless: bool = True, verbose: bool = False) -> str:
    """检测单个账号是否被封禁

    判定逻辑（按优先级）：
    1. 登录后检查URL是否含 'chat' → OK
    2. 检查多种输入框选择器 → OK
    3. 检查页面可见文本中是否有封禁短语 → banned
    4. 以上都不满足 → uncertain（不禁用）

    Args:
        username: 账号
        password: 密码
        headless: 是否无头模式
        verbose: 是否输出详细调试信息

    Returns:
        'ok': 账号正常（能进入聊天界面）
        'banned': 账号被封禁（明确看到封禁文案）
        'login_fail': 登录失败（密码错误等）
        'uncertain': 状态不确定（不自动禁用）
        'error': 检测过程异常
    """
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=headless, executable_path=BROWSER_PATH)
            context = browser.new_context()
            FingerprintRandomizer.randomize(context)
            page = context.new_page()

            # 访问 DeepSeek（不在首页做封禁检测，因为尚未登录）
            page.goto('https://chat.deepseek.com/', timeout=20000)
            time.sleep(3)

            if verbose:
                logger.info(f"[调试] 首页URL: {page.url}")

            # 点击登录按钮
            try:
                page.get_by_role("button").nth(2).click()
                time.sleep(1)
            except Exception:
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
                time.sleep(8)  # 等待登录响应
            except Exception as e:
                logger.warning(f"[封禁检测] 登录按钮点击失败: {e}")
                browser.close()
                return 'error'

            # ═══════════════════════════════════════════════════
            # 判定逻辑：先判成功，再判失败，兜底不禁用
            # ═══════════════════════════════════════════════════

            current_url = page.url
            if verbose:
                logger.info(f"[调试] 登录后URL: {current_url}")

            # ① 先判定成功：URL包含chat即为成功登录
            if 'chat' in current_url:
                if verbose:
                    logger.info(f"[调试] URL含'chat'，判定OK")
                browser.close()
                return 'ok'

            # ② 检查多种成功选择器
            SUCCESS_SELECTORS = [
                '[placeholder="Message DeepSeek"]',
                '[placeholder="给 DeepSeek 发送消息"]',
                'textarea',
                '.ds-chat-input',
            ]
            for selector in SUCCESS_SELECTORS:
                try:
                    page.wait_for_selector(selector, timeout=3000)
                    if verbose:
                        logger.info(f"[调试] 找到选择器 {selector}，判定OK")
                    browser.close()
                    return 'ok'
                except Exception:
                    continue

            # ③ 获取页面可见文本（不用 page.content()，避免匹配HTML属性）
            page_text = ''
            try:
                page_text = page.inner_text('body')
            except Exception:
                pass

            if verbose:
                logger.info(f"[调试] 页面可见文本前300字: {page_text[:300]}")

            # ④ 检查可见文本中是否有封禁短语
            for signal in BAN_SIGNALS:
                if signal in page_text:
                    if verbose:
                        logger.info(f"[调试] 匹配到封禁信号: '{signal}'")
                    browser.close()
                    return 'banned'

            # ⑤ 检查登录失败信号
            for signal in LOGIN_FAIL_SIGNALS:
                if signal.lower() in page_text.lower():
                    browser.close()
                    return 'login_fail'

            # ⑥ 再等5秒，二次确认
            time.sleep(5)
            current_url = page.url

            # 二次URL检查
            if 'chat' in current_url:
                browser.close()
                return 'ok'

            # 二次可见文本封禁检测
            try:
                page_text_2 = page.inner_text('body')
            except Exception:
                page_text_2 = ''

            for signal in BAN_SIGNALS:
                if signal in page_text_2:
                    browser.close()
                    return 'banned'

            # ⑦ 兜底：不确定（不禁用）
            if verbose:
                logger.info(f"[调试] 未能确认状态，URL={current_url}")
            browser.close()
            return 'uncertain'

    except Exception as e:
        logger.error(f"[封禁检测] 检测异常 {username}: {e}")
        return 'error'


def check_all_accounts(headless: bool = True):
    """遍历所有活跃 DeepSeek 账号，检测封禁状态"""
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
            _mark_banned(account_id, username, "页面可见文本中检测到封禁信号")
        elif status == 'login_fail':
            logger.warning(f"[封禁检测] ⚠️ 登录失败（密码错误?）: {username}")
        elif status == 'ok':
            logger.info(f"[封禁检测] ✅ 账号正常: {username}")
        elif status == 'uncertain':
            logger.warning(f"[封禁检测] ❓ 状态不确定（未禁用）: {username}")
        else:
            logger.warning(f"[封禁检测] ⚠️ 检测异常: {username}")

        # 每个账号间隔 5-15 秒
        if idx < total:
            wait = random.randint(5, 15)
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


def test_single_account(username: str, headless: bool = True):
    """测试单个账号（带详细调试输出）"""
    account = _get_account_by_username(username)
    if account is None:
        logger.error(f"[测试] 未找到账号: {username}")
        return

    logger.info(f"[测试] 开始检测: {username} (verbose=True)")
    status = _check_single_account(account['username'], account['password'], headless, verbose=True)
    logger.info(f"[测试] 检测结果: {status}")

    if status == 'banned':
        logger.warning(f"[测试] 该账号被判定为封禁")
    elif status == 'ok':
        logger.info(f"[测试] ✅ 该账号正常可用")
    elif status == 'uncertain':
        logger.info(f"[测试] ❓ 状态不确定（不会被禁用）")

    return status


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='DeepSeek 账号封禁检测工具')
    parser.add_argument('--show', action='store_true', help='显示浏览器（非无头模式）')
    parser.add_argument('--test', type=str, help='测试单个账号（带详细调试输出）')
    args = parser.parse_args()

    if args.test:
        test_single_account(args.test, headless=not args.show)
    else:
        check_all_accounts(headless=not args.show)
