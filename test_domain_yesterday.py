#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

# 查询昨天的数据
url = 'http://localhost:8080/api/domain/list?date=20260413&page=1&page_size=5&sort=score'
req = urllib.request.Request(url)
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    items = data.get('data', {}).get('items', [])
    print("=== 2026-04-13 的数据 ===")
    for item in items:
        size = item.get('news_size', 'N/A')
        score = str(item.get('composite_score', 'N/A'))
        title = item.get('key_event', '')[:50]
        print(f"{size:6s} | {score:4s} | {title}")
