#!/usr/bin/env python3
"""验证第12列是否匹配"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

# 获取债券表第12列的代码
with mysql_tool.engine.connect() as conn:
    rows = pd.read_sql("SELECT * FROM data_bond_ths", conn).to_dict('records')

bond_codes_12 = set()
for row in rows:
    values = list(row.values())
    stock_code = values[12]  # 第12列
    if stock_code:
        bond_codes_12.add(str(stock_code))

print(f"债券表第12列的代码数: {len(bond_codes_12)}")
print(f"示例: {list(bond_codes_12)[:5]}")

# 获取行业成分股的股票代码
with mysql_tool.engine.connect() as conn:
    rows = pd.read_sql("SELECT DISTINCT stock_code FROM data_industry_code_component_ths", conn)
    industry_codes = set(rows['stock_code'].astype(str).tolist())

print(f"\n行业成分股表的股票代码数: {len(industry_codes)}")

# 检查交集
cross = bond_codes_12 & industry_codes
print(f"\n交集数量: {len(cross)}")
print(f"匹配率: {len(cross) / len(bond_codes_12) * 100:.1f}%")

if cross:
    print(f"\n匹配示例: {list(cross)[:10]}")
