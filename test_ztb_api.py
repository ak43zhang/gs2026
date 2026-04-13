#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试涨停分析API"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.services.ztb_analysis_service import get_ztb_list, get_ztb_stats

# 测试列表查询
result = get_ztb_list(date='20260413', page_size=1000)
print(f"Total: {result['total']}")
print(f"Items count: {len(result['items'])}")
if result['items']:
    print(f"\nFirst item: {result['items'][0]}")
else:
    print("\nNo items found!")

# 测试统计查询
stats = get_ztb_stats(date='20260413')
print(f"\nStats: {stats}")
