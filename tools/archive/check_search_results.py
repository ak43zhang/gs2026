#!/usr/bin/env python3
"""检查拼音搜索返回的数据"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 初始化搜索器
searcher = stock_picker_service.init_pinyin_searcher()

print("=== 搜索 电力 ===")
results = searcher.search('电力', 5)
for r in results:
    print(f"  name={r['name']}, code={r['code']}, type={r['type']}")

print("\n=== 搜索 电子化学品 ===")
results = searcher.search('电子化学品', 5)
for r in results:
    print(f"  name={r['name']}, code={r['code']}, type={r['type']}")

print("\n=== 搜索 小家电 ===")
results = searcher.search('小家电', 5)
for r in results:
    print(f"  name={r['name']}, code={r['code']}, type={r['type']}")
