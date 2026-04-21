#!/usr/bin/env python3
"""查找有交集的行业对 - 简化版"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

# 确保缓存已加载
if not stock_picker_service._stock_cache:
    stock_picker_service.load_memory_cache()

# 查找同时有半导体和电子化学品的股票
cache = stock_picker_service._stock_cache

semi_codes = set()
chem_codes = set()

for code, data in cache.items():
    industries = data.get('industries', set())
    if '半导体' in industries:
        semi_codes.add(code)
    if '电子化学品' in industries:
        chem_codes.add(code)

print(f'半导体股票数: {len(semi_codes)}')
print(f'电子化学品股票数: {len(chem_codes)}')

# 检查交集
cross = semi_codes & chem_codes
print(f'同时属于两个行业的股票数: {len(cross)}')

if cross:
    print(f'示例: {list(cross)[:5]}')
else:
    print('没有股票同时属于半导体和电子化学品')
    
# 推荐测试组合：半导体 + 芯片概念
print()
print('=== 检查半导体 + 芯片概念 ===')
chip_concept_codes = set()
for code, data in cache.items():
    concepts = data.get('concepts', set())
    if '芯片概念' in concepts:
        chip_concept_codes.add(code)

print(f'芯片概念股票数: {len(chip_concept_codes)}')
cross2 = semi_codes & chip_concept_codes
print(f'同时属于半导体行业和芯片概念的股票数: {len(cross2)}')
if cross2:
    print(f'示例: {list(cross2)[:5]}')
