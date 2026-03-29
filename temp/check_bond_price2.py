#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查债券价格字段"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

import pandas as pd
from gs2026.utils import config_util
from sqlalchemy import create_engine

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 查看所有字段
print("表字段:")
df = pd.read_sql("SELECT * FROM data_bond_ths LIMIT 1", engine)
for col in df.columns:
    print(f"  {col}")

# 检查可能的债券价格字段
print("\n\n检查数值字段统计:")
for col in df.columns:
    if df[col].dtype in ['float64', 'int64']:
        stats = pd.read_sql(f"""
            SELECT 
                COUNT(*) as count,
                AVG(`{col}`) as avg_val,
                MIN(`{col}`) as min_val,
                MAX(`{col}`) as max_val
            FROM data_bond_ths
            WHERE `{col}` IS NOT NULL
        """, engine)
        print(f"\n{col}:")
        print(stats.to_string())
