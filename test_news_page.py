#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

# 测试新闻页面
req = urllib.request.Request('http://localhost:8080/news')
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8')
        print(f'Status: {resp.status}')
        print(f'Content length: {len(html)}')
        if '新闻分析' in html or '分析中心' in html:
            print('✅ 新闻页面加载成功')
        else:
            print('❌ 页面内容不正确')
        # 检查关键元素
        if 'news-container' in html:
            print('✅ 包含新闻容器')
        if 'news-list' in html:
            print('✅ 包含新闻列表')
except Exception as e:
    print(f'Error: {e}')

# 测试新闻API
print("\n测试新闻API:")
req2 = urllib.request.Request('http://localhost:8080/api/news/list?date=20260413&page=1&page_size=3')
try:
    with urllib.request.urlopen(req2, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f'Status: {data.get("code")}')
        print(f'Items: {len(data.get("data", {}).get("items", []))}')
except Exception as e:
    print(f'Error: {e}')
