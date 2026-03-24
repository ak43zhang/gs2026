"""
浏览器请求头设置
注意：Cookie已统一由 wencai_cookie_config.py 管理，不再在此硬编码
"""
from typing import Dict, Any

from playwright.sync_api import Browser, Page


def set_page_display_options_chrome(browser: Browser) -> Page:
    """
    设置Chrome浏览器页面显示选项
    
    注意：Cookie已统一由 wencai_cookie_config 管理。
    如需Cookie支持，请使用 load_wencai_context(browser) 替代此函数。

    Args:
        browser: Playwright浏览器实例

    Returns:
        配置好的页面实例
    """
    # 创建一个新的浏览器上下文
    context = browser.new_context()
    page = context.new_page()

    headers: Dict[str, str] = {
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Host': 'www.iwencai.com',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Chromium";v="145", "Not:A-Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }

    for key, value in headers.items():
        page.set_extra_http_headers({key: value})

    return page
