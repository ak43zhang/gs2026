#!/usr/bin/env python3
"""清空并重新预热缓存"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
from gs2026.dashboard2.services import stock_picker_service

print("=== 清空宽表 ===")
mysql_tool = mysql_util.get_mysql_tool()
from sqlalchemy import text
with mysql_tool.engine.connect() as conn:
    conn.execute(text("TRUNCATE TABLE cache_stock_industry_concept_bond"))
    conn.commit()
print("宽表已清空")

print("\n=== 重新预热缓存 ===")
stock_picker_service.warm_up_cache()
print("缓存预热完成")

print("\n=== 验证内存缓存 ===")
stock_picker_service.load_memory_cache()
print(f"内存缓存股票数: {len(stock_picker_service._stock_cache)}")

# 统计行业和概念
industry_count = 0
concept_count = 0
for code, data in stock_picker_service._stock_cache.items():
    if data.get('industries'):
        industry_count += 1
    if data.get('concepts'):
        concept_count += 1

print(f"有行业数据的股票数: {industry_count}")
print(f"有概念数据的股票数: {concept_count}")

# 显示样本
sample_code = list(stock_picker_service._stock_cache.keys())[0]
sample = stock_picker_service._stock_cache[sample_code]
print(f"\n样本股票 {sample_code}:")
print(f"  行业: {list(sample['industries'])[:3]}")
print(f"  概念: {list(sample['concepts'])[:3]}")
