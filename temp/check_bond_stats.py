#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查转股价格分布"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

import pandas as pd
from gs2026.utils import config_util
from sqlalchemy import create_engine

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 检查转股价格分布
df = pd.read_sql("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN `转股价格` >= 120 AND `转股价格` <= 250 THEN 1 ELSE 0 END) as in_range,
        SUM(CASE WHEN `转股价格` < 120 THEN 1 ELSE 0 END) as below_120,
        SUM(CASE WHEN `转股价格` > 250 THEN 1 ELSE 0 END) as above_250,
        AVG(`转股价格`) as avg_price,
        MIN(`转股价格`) as min_price,
        MAX(`转股价格`) as max_price
    FROM data_bond_ths
    WHERE `转股价格` IS NOT NULL
""", engine)

print("转股价格分布:")
print(df)

# 检查上市日期分布
df2 = pd.read_sql("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN `上市日期` IS NOT NULL AND `上市日期` <= CURDATE() THEN 1 ELSE 0 END) as listed,
        SUM(CASE WHEN `上市日期` IS NULL OR `上市日期` > CURDATE() THEN 1 ELSE 0 END) as not_listed
    FROM data_bond_ths
""", engine)

print("\n上市状态分布:")
print(df2)
