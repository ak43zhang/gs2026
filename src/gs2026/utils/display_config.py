"""
浏览器请求头设置
"""
from typing import Dict, Any

from playwright.sync_api import Browser, Page


def set_page_display_options_chrome(browser: Browser) -> Page:
    """
    设置Chrome浏览器页面显示选项

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
        'Cookie': '_clck=jfj22q%7C2%7Cg4g%7C0%7C0; cid=7a979a1d87e536f37c2cb23e265ba98c1773837139; other_uid=Ths_iwencai_Xuangu_cc8ac696c617ac573caa1543f2e63644; v=A0Ei5tgizCrVWyAejM8y_l49UIZebrJt3-FZdKOSOMCnGm_4677FMG8yaWww; _clsk=1k79mzinmz4p%7C1773839151413%7C9%7C1%7C',
        'Host': 'www.iwencai.com',
        'If-None-Match': 'W/"6980653d-3e44"',
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
