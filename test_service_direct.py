#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""直接测试修复后的服务"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.services.ztb_analysis_service import get_ztb_list

print("Testing get_ztb_list...")
result = get_ztb_list(date='20260413', page=1, page_size=3)
print(f"Items: {len(result.get('items', []))}")
print(f"Total: {result.get('total', 0)}")

for item in result.get('items', [])[:3]:
    name = item.get('stock_name', '')
    code = item.get('stock_code', '')
    print(f"  - {name} ({code})")
