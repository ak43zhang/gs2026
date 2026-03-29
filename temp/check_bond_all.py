#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查债券表所有字段"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

import pandas as pd
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 查看表结构
with engine.connect() as conn:
    result = conn.execute(text('SHOW COLUMNS FROM data_bond_ths'))
    columns = []
    for row in result:
        col_name = row[0]
        col_type = row[1]
        columns.append(col_name)
        print(f"{col_name}: {col_type}")

print(f"\n总字段数: {len(columns)}")

# 查看示例数据
print("\n示例数据:")
df = pd.read_sql("SELECT * FROM data_bond_ths LIMIT 1", engine)
for col in df.columns:
    val = df[col].iloc[0]
    print(f"  {col}: {val}")
