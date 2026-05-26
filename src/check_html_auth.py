#!/usr/bin/env python
"""带登录检查 Flask 返回的 backtest.html"""
import urllib.request
import urllib.parse
import http.cookiejar

# 创建 cookie 处理器
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 登录
login_data = urllib.parse.urlencode({'username': 'admin', 'password': 'admin123'}).encode()
opener.open('http://localhost:8080/login', login_data)

# 获取 backtest 页面
r = opener.open('http://localhost:8080/analysis/backtest')
html = r.read().decode('utf-8')

print(f"HTML length: {len(html)}")

for pattern in ['star-critical', 'star_color', 'starClass', 'star-normal']:
    idx = html.find(pattern)
    if idx >= 0:
        print(f"  [OK] '{pattern}' found at pos {idx}")
    else:
        print(f"  [MISSING] '{pattern}' NOT found")
