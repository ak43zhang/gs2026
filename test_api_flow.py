#!/usr/bin/env python3
"""模拟前端API请求测试"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service
import json

# 初始化服务
stock_picker_service.init_service()

# 模拟路由层的处理
tags_param = "industry:881147,industry:881173"

print(f"请求参数: tags={tags_param}")

# 解析 tags 参数
searcher = stock_picker_service.init_pinyin_searcher()
tag_map = {}
for item in searcher.items:
    tag_map[f"{item['type']}:{item['code']}"] = {
        'name': item['name'],
        'code': item['code'],
        'type': item['type']
    }

print(f"\ntag_map 中的key示例: {list(tag_map.keys())[:5]}")

# 查找选中的标签
selected_tags = []
for tag_str in tags_param.split(','):
    if tag_str in tag_map:
        selected_tags.append(tag_map[tag_str])
        print(f"  找到: {tag_str} -> {tag_map[tag_str]}")
    else:
        print(f"  未找到: {tag_str}")

print(f"\n选中的标签: {selected_tags}")

if selected_tags:
    result = stock_picker_service.query_cross_stocks(selected_tags)
    print(f"\n查询结果摘要: {result['summary']}")
    print(f"分组数量: {len(result['groups'])}")
    for g in result['groups']:
        print(f"  {g['label']}: {len(g['stocks'])} 只股票")
else:
    print("\n没有选中的标签，查询失败！")
