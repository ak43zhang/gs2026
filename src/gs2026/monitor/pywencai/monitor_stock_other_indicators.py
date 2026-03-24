"""
问财其他指标监控 - 使用pywencai库
Cookie从统一配置文件加载
"""
import json
from pathlib import Path

import pywencai

from gs2026.utils.wencai_cookie_config import COOKIE_FILE, has_cookie


def get_cookie_string() -> str:
    """从Cookie文件中提取Cookie字符串（pywencai需要字符串格式）"""
    if not has_cookie():
        raise ValueError(f"Cookie文件不存在或无效: {COOKIE_FILE}")
    
    with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 将Playwright格式的Cookie转换为字符串格式
    cookies = data.get('cookies', [])
    
    # 只取iwencai相关域名的cookie
    cookie_parts = []
    for c in cookies:
        domain = c.get('domain', '')
        if 'iwencai' in domain or 'ths' in domain or 'hexin' in domain:
            cookie_parts.append(f"{c['name']}={c['value']}")
    
    return '; '.join(cookie_parts)


def query_wencai(query: str, loop: bool = True):
    """
    使用pywencai查询问财
    
    Args:
        query: 查询条件
        loop: 是否自动获取所有数据
    
    Returns:
        DataFrame
    """
    cookie_str = get_cookie_string()
    df = pywencai.get(
        query=query,
        cookie=cookie_str,
        loop=loop
    )
    return df


if __name__ == "__main__":
    df = query_wencai("主力净量")
    print(df)
