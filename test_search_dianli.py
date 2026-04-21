#!/usr/bin/env python3
"""测试搜索电力返回的代码"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 初始化搜索器
searcher = stock_picker_service.init_pinyin_searcher()

print("=== 搜索 电力 ===")
results = searcher.search('电力', 5)
for r in results:
    print(f"  name={r['name']}, code={r['code']}, type={r['type']}")

print("\n=== 验证 tag_map ===")
tag_map = {}
for item in searcher.items:
    tag_map[f"{item['type']}:{item['code']}"] = {
        'name': item['name'],
        'code': item['code'],
        'type': item['type']
    }

print(f"tag_map 数量: {len(tag_map)}")
print(f"包含 industry:881145 吗? {'industry:881145' in tag_map}")
print(f"包含 industry:881147 吗? {'industry:881147' in tag_map}")

if 'industry:881145' in tag_map:
    print(f"industry:881145 -> {tag_map['industry:881145']}")
