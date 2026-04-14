#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.services import domain_analysis_service

# 测试服务层返回的数据
result = domain_analysis_service.get_domain_list(date='20260413', sort_by='score', page=1, page_size=5)
items = result.get('items', [])
print("=== 服务层返回的数据 ===")
for item in items:
    size = item.get('news_size', 'N/A')
    score = str(item.get('composite_score', 'N/A'))
    title = item.get('key_event', '')[:50]
    print(f"{size:6s} | {score:4s} | {title}")
