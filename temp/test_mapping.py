#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试映射函数"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.monitor.stock_bond_industry_mapping import get_stock_bond_industry_mapping

# 测试函数
df = get_stock_bond_industry_mapping(min_convert_price=10, max_convert_price=200)
print(f'记录数: {len(df)}')
print(f'有债券: {df["bond_code"].notna().sum()}')
print(f'无债券: {df["bond_code"].isna().sum()}')
print('\n前5条:')
print(df.head().to_string())
