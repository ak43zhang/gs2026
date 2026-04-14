#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.services.news_service import get_news_list

print("Testing news service...")
result = get_news_list(date='20260413', page=1, page_size=3)
print(f"Source: {result.get('source')}")
print(f"Items: {len(result.get('items', []))}")
print(f"Total: {result.get('total', 0)}")

if result.get('items'):
    item = result['items'][0]
    print(f"First item: {item.get('title', 'N/A')[:30]}...")
