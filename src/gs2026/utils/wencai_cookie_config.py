"""
问财Cookie配置模块
用于统一管理同花顺问财的Cookie加载

使用方法：
    from gs2026.utils.wencai_cookie_config import load_wencai_context
    
    with sync_playwright() as p:
        browser = p.chromium.launch(...)
        context = load_wencai_context(browser)
        page = context.new_page()
"""

import json
from pathlib import Path
from typing import Optional

# 项目根目录（从当前文件推导：utils -> gs2026 -> src -> 项目根）
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Cookie文件路径
COOKIE_FILE = PROJECT_ROOT / "configs" / "wencai_cookies.json"


def has_cookie() -> bool:
    """检查Cookie文件是否存在且有效"""
    if not COOKIE_FILE.exists():
        return False
    
    try:
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return 'cookies' in data and len(data['cookies']) > 0
    except:
        return False


def load_wencai_context(browser, viewport: Optional[dict] = None):
    """
    加载问财Cookie并创建浏览器上下文
    
    Args:
        browser: Playwright浏览器实例
        viewport: 视口大小，默认1920x1080
    
    Returns:
        BrowserContext: 浏览器上下文
    """
    if viewport is None:
        viewport = {'width': 1920, 'height': 1080}
    
    if has_cookie():
        return browser.new_context(
            storage_state=str(COOKIE_FILE),
            viewport=viewport
        )
    else:
        return browser.new_context(viewport=viewport)
