# -*- coding: utf-8 -*-
"""诊断API 567 - 测试不同请求头组合"""
import requests

API_URL = 'https://np-cnotice-stock.eastmoney.com/api/content/ann'
TEST_CODE = 'AN202604301821789162'
PARAMS = {'art_code': TEST_CODE, 'client_source': 'web', 'page_index': 1}

# 方案1：最小请求头（当前）
headers_minimal = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/'
}

# 方案2：完整浏览器请求头
headers_full = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://data.eastmoney.com/notices/detail/300716/AN202604301821789162.html',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Origin': 'https://data.eastmoney.com',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
}

# 方案3：仅补 Accept + Origin
headers_mid = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://data.eastmoney.com/',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://data.eastmoney.com',
}

# 方案4：加Cookie（先访问主站获取）
def get_cookie_headers():
    s = requests.Session()
    # 先访问公告列表页获取cookie
    s.get('https://data.eastmoney.com/notices/', headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }, timeout=10)
    cookies = s.cookies.get_dict()
    print(f'  获取到cookies: {list(cookies.keys())}')
    return s, cookies

tests = [
    ('最小请求头', headers_minimal, None),
    ('完整浏览器头', headers_full, None),
    ('中等请求头', headers_mid, None),
]

for name, headers, session in tests:
    print(f'\n=== {name} ===')
    try:
        r = requests.get(API_URL, params=PARAMS, headers=headers, timeout=10)
        print(f'  Status: {r.status_code}')
        if r.status_code == 200:
            data = r.json().get('data', {})
            content = (data.get('notice_content') or '')[:60]
            print(f'  Content: {content}')
        else:
            print(f'  Body[:200]: {r.text[:200]}')
    except Exception as e:
        print(f'  ERROR: {type(e).__name__}: {e}')

# 方案4：带cookie
print(f'\n=== 带Cookie ===')
try:
    s, cookies = get_cookie_headers()
    s.headers.update(headers_full)
    r = s.get(API_URL, params=PARAMS, timeout=10)
    print(f'  Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json().get('data', {})
        content = (data.get('notice_content') or '')[:60]
        print(f'  Content: {content}')
    else:
        print(f'  Body[:200]: {r.text[:200]}')
except Exception as e:
    print(f'  ERROR: {type(e).__name__}: {e}')

print('\ndone')
