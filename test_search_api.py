#!/usr/bin/env python3
"""测试搜索API"""
import sys
sys.path.insert(0, 'src')
from gs2026.dashboard2.services import stock_picker_service

# 测试搜索
print("=== 测试搜索 '电' ===")
results = stock_picker_service.search_tags('电', 10)
print(f"结果数: {len(results)}")
for r in results:
    print(f"  {r['type']}: {r['name']} ({r['code']})")

print("\n=== 测试搜索 '电力' ===")
results = stock_picker_service.search_tags('电力', 10)
print(f"结果数: {len(results)}")
for r in results:
    print(f"  {r['type']}: {r['name']} ({r['code']})")

print("\n=== 测试搜索 'dianli' ===")
results = stock_picker_service.search_tags('dianli', 10)
print(f"结果数: {len(results)}")
for r in results:
    print(f"  {r['type']}: {r['name']} ({r['code']})")

print("\n=== 测试搜索 'dl' ===")
results = stock_picker_service.search_tags('dl', 10)
print(f"结果数: {len(results)}")
for r in results:
    print(f"  {r['type']}: {r['name']} ({r['code']})")
