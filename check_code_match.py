#!/usr/bin/env python3
"""检查代码匹配问题"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

# 获取债券映射
with mysql_tool.engine.connect() as conn:
    rows = pd.read_sql("SELECT * FROM data_bond_ths", conn).to_dict('records')

bond_codes = set()
for row in rows:
    values = list(row.values())
    stock_code = values[4]  # 第4列
    if stock_code:
        bond_codes.add(str(stock_code))

print(f"债券表中的正股代码数: {len(bond_codes)}")
print(f"示例: {list(bond_codes)[:5]}")

# 获取行业成分股的股票代码
with mysql_tool.engine.connect() as conn:
    rows = pd.read_sql("SELECT DISTINCT stock_code FROM data_industry_code_component_ths", conn)
    industry_codes = set(rows['stock_code'].astype(str).tolist())

print(f"\n行业成分股表的股票代码数: {len(industry_codes)}")
print(f"示例: {list(industry_codes)[:5]}")

# 检查交集
cross = bond_codes & industry_codes
print(f"\n交集数量: {len(cross)}")
print(f"只在债券表中的代码数: {len(bond_codes - industry_codes)}")
print(f"只在行业表中的代码数: {len(industry_codes - bond_codes)}")

# 显示不匹配的示例
if bond_codes - industry_codes:
    print(f"\n债券表中但不在行业表中的代码示例: {list(bond_codes - industry_codes)[:5]}")
if industry_codes - bond_codes:
    print(f"行业表中但不在债券表中的代码示例: {list(industry_codes - bond_codes)[:5]}")
