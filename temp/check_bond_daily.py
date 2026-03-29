#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 data_bond_daily 表"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

import pandas as pd
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 查看表结构
print("data_bond_daily 表结构:")
with engine.connect() as conn:
    result = conn.execute(text('SHOW COLUMNS FROM data_bond_daily'))
    for row in result:
        print(f"  {row[0]}: {row[1]}")

# 查看示例数据
print("\n示例数据:")
df = pd.read_sql("SELECT * FROM data_bond_daily LIMIT 3", engine)
print(df.to_string())

# 检查价格字段统计
print("\n价格字段统计:")
stats = pd.read_sql("""
    SELECT 
        COUNT(*) as count,
        AVG(`close`) as avg_close,
        MIN(`close`) as min_close,
        MAX(`close`) as max_close
    FROM data_bond_daily
    WHERE `close` IS NOT NULL
""", engine)
print(stats.to_string())
