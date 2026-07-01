"""DeepSeek 账号封禁检测工具

遍历所有 is_active=1 的 DeepSeek 账号，逐个尝试登录，
检测是否被封禁/临时停用，将封禁账号的 is_active 设置为 0。

使用方式：
    python -m gs2026.tools.deepseek_ban_checker
    python -m gs2026.tools.deepseek_ban_checker --show
    python -m gs2026.tools.deepseek_ban_checker --test brittanydavis5629@outlook.com --show

判定原则：
- 封禁检测优先级 > 成功判定（先查封禁，再确认成功）
- 只检查页面可见文本，不检查原始HTML
- 未确认状态标记为 uncertain，不自动禁用
"""

import time
import random
from pathlib import Path
from typing import List, Dict, Optional

from playwright.sync_api import sync_playwright
from sqlalchemy import text

from gs2026.utils import config_util, log_util, string_enum
from gs2026.analysis.worker.message.deepseek.browser.anti_block import (
    FingerprintRandomizer, DelayBox
)

logger = log_util.setup_logger(str(Path(__file__).absolute()))

# 数据库配置
url: str = config_util.get_config("common.url")
engine = config_util.get_engine()

# Firefox 浏览器路径
BROWSER_PATH: str = string_enum.FIREFOX_PATH_1509

# ★ 封禁信号关键词（精确短语）
# 只在 page.inner_text() 可见文本中匹配，不会误判HTML属性
BAN_SIGNALS = [
    # 二级封禁（无法使用）
    '账号已被临时停用',
    '账号已被停用',
    '你的账号已被',
    '临时停用',
    '账号异常',
    '账号被封',
    'Your account has been suspended',
    'account has been temporarily suspended',
    'account is restricted',
    # 一级限制（能登录但功能受限）
    '功能受限',
    '账号受限',
    '操作受限',
    '已被限制',
    '暂时无法使用',
    '违规',
    'restricted',
    'suspended',
    'violation',
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


def _get_account_by_username(username: str) -> Optional[Dict]:
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


def _check_ban_in_text(page_text: str, verbose: bool = False) -> Optional[str]:
    """检查可见文本中是否有封禁信号

    Returns:
        匹配到的信号字符串，或 None（未匹配）
    """
    for signal in BAN_SIGNALS:
        if signal in page_text:
            if verbose:
                logger.info(f"[调试] 匹配到封禁信号: '{signal}'")
            return signal
    return None


def _check_single_account(username: str, password: str, headless: bool = True, verbose: bool = False) -> str:
    """检测单个账号是否被封禁

    判定逻辑（修正版）：
    1. 登录 → 等待
    2. 获取页面可见文本 → 检查封禁信号（优先级最高）
    3. 检查URL/选择器判定成功
    4. 二次等待确认
    5. 兜底 uncertain

    Returns:
        'ok': 账号正常
        'banned': 账号被封禁
        'login_fail': 登录失败
        'uncertain': 状态不确定（不禁用）
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
                time.sleep(8)
            except Exception as e:
                logger.warning(f"[封禁检测] 登录按钮点击失败: {e}")
                browser.close()
                return 'error'

            # ═══════════════════════════════════════════════════
            # 判定逻辑：先查封禁（优先级最高），再判成功
            # ═══════════════════════════════════════════════════

            current_url = page.url
            if verbose:
                logger.info(f"[调试] 登录后URL: {current_url}")

            # ① 获取页面可见文本
            page_text = ''
            try:
                page_text = page.inner_text('body')
            except Exception:
                pass

            if verbose:
                logger.info(f"[调试] 页面可见文本（前500字）:\n{page_text[:500]}")

            # ② 最高优先级：检查封禁信号
            ban_signal = _check_ban_in_text(page_text, verbose)
            if ban_signal:
                logger.warning(f"[封禁检测] 检测到封禁信号: '{ban_signal}'")
                browser.close()
                return 'banned'

            # ③ 检查登录失败信号
            for signal in LOGIN_FAIL_SIGNALS:
                if signal.lower() in page_text.lower():
                    if verbose:
                        logger.info(f"[调试] 匹配到登录失败信号: '{signal}'")
                    browser.close()
                    return 'login_fail'

            # ④ 判定成功：URL含chat且不在登录页 或 找到输入框
            # 注意：chat.deepseek.com/sign_in 也含'chat'，必须排除登录页
            is_chat_page = 'chat' in current_url and '/sign_in' not in current_url and '/sign_up' not in current_url
            if is_chat_page:
                if verbose:
                    logger.info(f"[调试] URL为聊天页面（非登录页），且无封禁信号，判定OK")
                browser.close()
                return 'ok'

            # 如果还在登录页（login没有跳转），说明登录被静默拒绝
            if '/sign_in' in current_url or '/sign_up' in current_url:
                # 检查页面是否仍显示登录表单
                login_form_signals = ['Log in', 'Sign up', 'Forgot password']
                login_form_count = sum(1 for s in login_form_signals if s in page_text)
                if login_form_count >= 2:
                    if verbose:
                        logger.info(f"[调试] 登录后仍在sign_in页面，登录被静默拒绝（疑似封禁）")
                    browser.close()
                    return 'banned'

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
                        logger.info(f"[调试] 找到选择器 {selector}，且无封禁信号，判定OK")
                    browser.close()
                    return 'ok'
                except Exception:
                    continue

            # ⑤ 二次等待确认（可能页面还在加载）
            time.sleep(5)
            current_url = page.url

            # 二次获取可见文本
            try:
                page_text_2 = page.inner_text('body')
            except Exception:
                page_text_2 = ''

            if verbose:
                logger.info(f"[调试] 二次页面可见文本（前500字）:\n{page_text_2[:500]}")

            # 二次封禁检测
            ban_signal_2 = _check_ban_in_text(page_text_2, verbose)
            if ban_signal_2:
                browser.close()
                return 'banned'

            # 二次成功判定
            is_chat_page_2 = 'chat' in current_url and '/sign_in' not in current_url and '/sign_up' not in current_url
            if is_chat_page_2:
                browser.close()
                return 'ok'

            # ⑥ 兜底：不确定
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
        return 'not_found'

    logger.info(f"[测试] 开始检测: {username} (verbose=True, headless={headless})")
    status = _check_single_account(account['username'], account['password'], headless, verbose=True)
    logger.info(f"[测试] ═══ 检测结果: {status} ═══")

    if status == 'banned':
        logger.warning(f"[测试] ❌ 该账号被判定为封禁")
    elif status == 'ok':
        logger.info(f"[测试] ✅ 该账号正常可用")
    elif status == 'uncertain':
        logger.info(f"[测试] ❓ 状态不确定（不会被禁用）")
    elif status == 'login_fail':
        logger.warning(f"[测试] ⚠️ 登录失败")

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
