#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查转股价格分布详情"""
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
        `债券代码`, `债券简称`, `正股代码`, `正股简称`, `转股价格`, `上市日期`
    FROM data_bond_ths
    WHERE `转股价格` IS NOT NULL
    ORDER BY `转股价格` DESC
    LIMIT 20
""", engine)

print("转股价格最高的20条:")
print(df.to_string())

print("\n\n转股价格分布区间:")
df2 = pd.read_sql("""
    SELECT 
        CASE 
            WHEN `转股价格` < 10 THEN '<10'
            WHEN `转股价格` >= 10 AND `转股价格` < 20 THEN '10-20'
            WHEN `转股价格` >= 20 AND `转股价格` < 30 THEN '20-30'
            WHEN `转股价格` >= 30 AND `转股价格` < 50 THEN '30-50'
            WHEN `转股价格` >= 50 AND `转股价格` < 100 THEN '50-100'
            WHEN `转股价格` >= 100 THEN '>=100'
        END as price_range,
        COUNT(*) as count
    FROM data_bond_ths
    WHERE `转股价格` IS NOT NULL
    GROUP BY price_range
    ORDER BY count DESC
""", engine)
print(df2.to_string())
