#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import urllib.error

routes = [
    ('/ztb-analysis', '涨停分析'),
    ('/news-analysis', '新闻分析'),
    ('/notice-analysis', '公告分析'),
    ('/domain-analysis', '领域分析'),
]

base_url = 'http://localhost:8080'

print('=' * 60)
print('路由测试')
print('=' * 60)

all_pass = True
for route, name in routes:
    url = base_url + route
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8')
            title_start = html.find('<title>')
            title_end = html.find('</title>')
            title = html[title_start+7:title_end] if title_start > 0 else 'No title'
            status = '✅' if resp.status == 200 else '❌'
            print(f'{status} {name:12s} {route:20s} -> {title}')
    except urllib.error.HTTPError as e:
        print(f'❌ {name:12s} {route:20s} -> HTTP {e.code}')
        all_pass = False
    except Exception as e:
        print(f'❌ {name:12s} {route:20s} -> Error: {str(e)[:30]}')
        all_pass = False

print('=' * 60)
print('全部通过' if all_pass else '有路由失败')
print('=' * 60)
