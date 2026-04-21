#!/usr/bin/env python3
"""检查概念数据"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 确保缓存已加载
if not stock_picker_service._stock_cache:
    stock_picker_service.load_memory_cache()

cache = stock_picker_service._stock_cache

# 统计有概念的股票
has_concept = 0
all_concepts = set()

for code, data in cache.items():
    concepts = data.get('concepts', set())
    if concepts:
        has_concept += 1
        all_concepts.update(concepts)

print(f'有概念的股票数: {has_concept}')
print(f'概念总数: {len(all_concepts)}')

# 显示前20个概念
print('\n前20个概念:')
for c in sorted(list(all_concepts))[:20]:
    print(f'  {c}')

# 查找包含"芯片"的概念
chip_concepts = [c for c in all_concepts if '芯片' in c]
print(f'\n包含芯片的概念: {chip_concepts}')
