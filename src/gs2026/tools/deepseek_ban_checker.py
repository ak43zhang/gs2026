"""DeepSeek 账号封禁检测工具（并发优化版）

遍历所有 DeepSeek 账号，并发检测状态：
- 正常账号 → is_active=1
- 封禁账号 → is_active=0

优化点：
1. 复用单个浏览器实例，多Context并发
2. 智能等待替代固定sleep
3. 并发检测（默认4并发）
4. 缩短账号间隔

使用方式：
    python -m gs2026.tools.deepseek_ban_checker
    python -m gs2026.tools.deepseek_ban_checker --show
    python -m gs2026.tools.deepseek_ban_checker --test brittanydavis5629@outlook.com --show
    python -m gs2026.tools.deepseek_ban_checker --workers 6

判定原则：
- 封禁检测优先级 > 成功判定（先查封禁，再确认成功）
- 只检查页面可见文本，不检查原始HTML
- 未确认状态标记为 uncertain，不修改 is_active
"""

import time
import random
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from playwright.sync_api import sync_playwright, Browser, BrowserContext
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

# 并发数
DEFAULT_WORKERS = 4

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

# 成功选择器
SUCCESS_SELECTORS = [
    '[placeholder="Message DeepSeek"]',
    '[placeholder="给 DeepSeek 发送消息"]',
    'textarea',
    '.ds-chat-input',
]


def _get_all_accounts() -> List[Dict]:
    """获取所有 DeepSeek 账号（不论 is_active 状态）"""
    with engine.connect() as conn:
        sql = text("SELECT id, username, password, is_active FROM accounts WHERE service_type='deepseek'")
        result = conn.execute(sql)
        return [{"id": row[0], "username": row[1], "password": row[2], "is_active": row[3]} for row in result]


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


def _mark_active(account_id: int, username: str):
    """将账号标记为 is_active=1"""
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE accounts SET is_active=1 WHERE id=:id"
        ), {"id": account_id})
    logger.info(f"[封禁检测] ✅ 已激活账号 id={account_id} username={username}")


def _check_ban_in_text(page_text: str, verbose: bool = False) -> Optional[str]:
    """检查可见文本中是否有封禁信号"""
    for signal in BAN_SIGNALS:
        if signal in page_text:
            if verbose:
                logger.info(f"[调试] 匹配到封禁信号: '{signal}'")
            return signal
    return None


def _smart_wait_for_login(page, timeout_ms: int = 12000, verbose: bool = False) -> bool:
    """智能等待登录完成（替代固定sleep(8)）
    
    等待条件（任一满足即返回）：
    1. URL变化（离开sign_in页面）
    2. 出现聊天输入框
    3. 出现封禁/错误文本
    4. 超时
    
    Returns:
        True=检测到变化, False=超时
    """
    start = time.time()
    initial_url = page.url
    check_interval = 0.5  # 每500ms检查一次
    
    while (time.time() - start) * 1000 < timeout_ms:
        current_url = page.url
        
        # URL变化 → 登录有响应了
        if current_url != initial_url:
            if verbose:
                logger.info(f"[智能等待] URL变化: {initial_url} → {current_url}")
            time.sleep(1)  # 给页面1s渲染时间
            return True
        
        # 检查是否出现成功选择器
        for selector in SUCCESS_SELECTORS:
            try:
                if page.query_selector(selector):
                    if verbose:
                        logger.info(f"[智能等待] 找到选择器: {selector}")
                    return True
            except Exception:
                pass
        
        # 检查页面文本是否有封禁信号（快速判定）
        try:
            body_text = page.inner_text('body')
            if _check_ban_in_text(body_text):
                return True
            # 检查登录失败
            for signal in LOGIN_FAIL_SIGNALS:
                if signal.lower() in body_text.lower():
                    return True
        except Exception:
            pass
        
        time.sleep(check_interval)
    
    if verbose:
        logger.info(f"[智能等待] 超时 {timeout_ms}ms")
    return False


def _check_single_account(username: str, password: str, browser: Browser, 
                          headless: bool = True, verbose: bool = False) -> str:
    """检测单个账号是否被封禁（复用浏览器实例）

    Returns:
        'ok': 账号正常
        'banned': 账号被封禁
        'login_fail': 登录失败
        'uncertain': 状态不确定（不禁用）
        'error': 检测过程异常
    """
    context = None
    try:
        # 创建独立Context（隔离cookie/指纹）
        context = browser.new_context()
        FingerprintRandomizer.randomize(context)
        page = context.new_page()

        # 访问 DeepSeek（用wait_for_load_state替代固定sleep）
        page.goto('https://chat.deepseek.com/', timeout=20000)
        page.wait_for_load_state('domcontentloaded', timeout=10000)
        time.sleep(1)  # 最小等待让JS执行

        if verbose:
            logger.info(f"[调试] 首页URL: {page.url}")

        # 点击登录按钮
        try:
            page.get_by_role("button").nth(2).click()
            time.sleep(0.5)
        except Exception:
            pass

        # 输入账号
        try:
            phone_input = page.get_by_placeholder("Phone number / email address")
            phone_input.fill(username)
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"[封禁检测] 找不到账号输入框: {e}")
            return 'error'

        # 输入密码
        try:
            pwd_input = page.get_by_placeholder("Password")
            pwd_input.fill(password)
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"[封禁检测] 找不到密码输入框: {e}")
            return 'error'

        # 点击登录 + 智能等待
        try:
            page.get_by_role("button", name="Log in").click()
            _smart_wait_for_login(page, timeout_ms=12000, verbose=verbose)
        except Exception as e:
            logger.warning(f"[封禁检测] 登录按钮点击失败: {e}")
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
            return 'banned'

        # ③ 检查登录失败信号
        for signal in LOGIN_FAIL_SIGNALS:
            if signal.lower() in page_text.lower():
                if verbose:
                    logger.info(f"[调试] 匹配到登录失败信号: '{signal}'")
                return 'login_fail'

        # ④ 判定成功：URL含chat且不在登录页
        is_chat_page = 'chat' in current_url and '/sign_in' not in current_url and '/sign_up' not in current_url
        if is_chat_page:
            if verbose:
                logger.info(f"[调试] URL为聊天页面，且无封禁信号，判定OK")
            return 'ok'

        # 如果还在登录页，说明登录被静默拒绝
        if '/sign_in' in current_url or '/sign_up' in current_url:
            login_form_signals = ['Log in', 'Sign up', 'Forgot password']
            login_form_count = sum(1 for s in login_form_signals if s in page_text)
            if login_form_count >= 2:
                if verbose:
                    logger.info(f"[调试] 登录后仍在sign_in页面，登录被静默拒绝")
                return 'banned'

        # ⑤ 检查成功选择器
        for selector in SUCCESS_SELECTORS:
            try:
                page.wait_for_selector(selector, timeout=2000)
                if verbose:
                    logger.info(f"[调试] 找到选择器 {selector}，判定OK")
                return 'ok'
            except Exception:
                continue

        # ⑥ 短暂二次确认（缩短到2秒）
        time.sleep(2)
        current_url = page.url

        try:
            page_text_2 = page.inner_text('body')
        except Exception:
            page_text_2 = ''

        ban_signal_2 = _check_ban_in_text(page_text_2, verbose)
        if ban_signal_2:
            return 'banned'

        is_chat_page_2 = 'chat' in current_url and '/sign_in' not in current_url and '/sign_up' not in current_url
        if is_chat_page_2:
            return 'ok'

        # ⑦ 兜底
        if verbose:
            logger.info(f"[调试] 未能确认状态，URL={current_url}")
        return 'uncertain'

    except Exception as e:
        logger.error(f"[封禁检测] 检测异常 {username}: {e}")
        return 'error'
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass


def _check_single_account_standalone(username: str, password: str, 
                                     headless: bool = True, verbose: bool = False) -> str:
    """独立浏览器检测单个账号（用于单账号测试）"""
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=headless, executable_path=BROWSER_PATH)
            result = _check_single_account(username, password, browser, headless, verbose)
            browser.close()
            return result
    except Exception as e:
        logger.error(f"[封禁检测] 检测异常 {username}: {e}")
        return 'error'


def _worker_check_accounts(accounts: List[Dict], worker_id: int, 
                           headless: bool = True) -> Dict[str, int]:
    """单个Worker：独立浏览器实例，串行检测分配给它的账号"""
    results = {"ok": 0, "banned": 0, "login_fail": 0, "error": 0, "uncertain": 0}
    
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=headless, executable_path=BROWSER_PATH)
            
            for idx, account in enumerate(accounts):
                account_id = account["id"]
                username = account["username"]
                password = account["password"]
                
                logger.info(f"[Worker-{worker_id}] ({idx+1}/{len(accounts)}) 检测: {username}")
                
                status = _check_single_account(username, password, browser, headless)
                results[status] += 1
                
                if status == 'banned':
                    _mark_banned(account_id, username, "页面可见文本中检测到封禁信号")
                elif status == 'login_fail':
                    _mark_banned(account_id, username, "登录失败（密码错误或账号不存在）")
                elif status == 'ok':
                    _mark_active(account_id, username)
                elif status == 'uncertain':
                    logger.warning(f"[Worker-{worker_id}] ❓ 状态不确定: {username}")
                else:
                    logger.warning(f"[Worker-{worker_id}] ⚠️ 检测异常: {username}")
                
                # 账号间隔缩短（Context已隔离，风险低）
                if idx < len(accounts) - 1:
                    wait = random.uniform(2, 5)
                    time.sleep(wait)
            
            browser.close()
    except Exception as e:
        logger.error(f"[Worker-{worker_id}] 浏览器异常: {e}")
    
    return results


def check_all_accounts(headless: bool = True, workers: int = DEFAULT_WORKERS):
    """并发检测所有 DeepSeek 账号
    
    Args:
        headless: 是否无头模式
        workers: 并发Worker数（每个Worker一个浏览器实例）
    """
    accounts = _get_all_accounts()
    total = len(accounts)
    
    if total == 0:
        logger.info("[封禁检测] 无账号需要检测")
        return
    
    # 调整worker数不超过账号数
    actual_workers = min(workers, total)
    logger.info(f"[封禁检测] 开始检测，共 {total} 个账号，{actual_workers} 并发")
    
    start_time = time.time()
    
    # 将账号均匀分配给各Worker
    chunks = [[] for _ in range(actual_workers)]
    for i, account in enumerate(accounts):
        chunks[i % actual_workers].append(account)
    
    # 并发执行
    all_results = {"ok": 0, "banned": 0, "login_fail": 0, "error": 0, "uncertain": 0}
    
    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = {
            executor.submit(_worker_check_accounts, chunk, worker_id, headless): worker_id
            for worker_id, chunk in enumerate(chunks, 1)
        }
        
        for future in as_completed(futures):
            worker_id = futures[future]
            try:
                result = future.result()
                for key in all_results:
                    all_results[key] += result[key]
            except Exception as e:
                logger.error(f"[Worker-{worker_id}] 执行失败: {e}")
    
    elapsed = time.time() - start_time
    
    # 汇总报告
    logger.info("=" * 50)
    logger.info(f"[封禁检测] 检测完成！耗时: {elapsed:.1f}s（{elapsed/total:.1f}s/账号）")
    logger.info(f"  ✅ 正常: {all_results['ok']}")
    logger.info(f"  ❌ 封禁（已禁用）: {all_results['banned']}")
    logger.info(f"  ❓ 不确定（未禁用）: {all_results['uncertain']}")
    logger.info(f"  ⚠️ 登录失败: {all_results['login_fail']}")
    logger.info(f"  💥 异常: {all_results['error']}")
    logger.info(f"  📊 并发数: {actual_workers} | 总账号: {total}")
    logger.info("=" * 50)

    return all_results


def test_single_account(username: str, headless: bool = True):
    """测试单个账号（带详细调试输出）"""
    account = _get_account_by_username(username)
    if account is None:
        logger.error(f"[测试] 未找到账号: {username}")
        return 'not_found'

    logger.info(f"[测试] 开始检测: {username} (verbose=True, headless={headless})")
    status = _check_single_account_standalone(
        account['username'], account['password'], headless, verbose=True
    )
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

    parser = argparse.ArgumentParser(description='DeepSeek 账号封禁检测工具（并发优化版）')
    parser.add_argument('--show', action='store_true', help='显示浏览器（非无头模式）')
    parser.add_argument('--test', type=str, help='测试单个账号（带详细调试输出）')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help=f'并发数（默认{DEFAULT_WORKERS}）')
    args = parser.parse_args()

    if args.test:
        test_single_account(args.test, headless=not args.show)
    else:
        check_all_accounts(headless=not args.show, workers=args.workers)


# ═══════════════════════════════════════════════════════
# 公共检测函数（供session.py等调用）
# ═══════════════════════════════════════════════════════

def check_ban_in_text(page_text: str) -> Optional[str]:
    """检查页面文本中是否有封禁信号（纯文本检测，无浏览器依赖）
    
    Args:
        page_text: 页面可见文本
        
    Returns:
        匹配到的封禁信号字符串，或None
    """
    for signal in BAN_SIGNALS:
        if signal in page_text:
            return signal
    return None
