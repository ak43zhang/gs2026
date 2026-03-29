#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试债券价格查询性能"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

import pandas as pd
from gs2026.utils import config_util
from sqlalchemy import create_engine, text
import time

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 测试1：子查询方式
print("测试1：子查询方式...")
start = time.time()
try:
    df1 = pd.read_sql("""
        SELECT 
            bond_code,
            close as bond_price,
            date as price_date
        FROM data_bond_daily
        WHERE (bond_code, date) IN (
            SELECT bond_code, MAX(date)
            FROM data_bond_daily
            GROUP BY bond_code
        )
        AND close >= 120
        AND close <= 250
    """, engine)
    print(f"  结果: {len(df1)} 条, 耗时: {time.time()-start:.2f}秒")
except Exception as e:
    print(f"  失败: {e}")

# 测试2：JOIN方式（更高效）
print("\n测试2：JOIN方式...")
start = time.time()
try:
    df2 = pd.read_sql("""
        SELECT d.bond_code, d.close as bond_price, d.date as price_date
        FROM data_bond_daily d
        INNER JOIN (
            SELECT bond_code, MAX(date) as max_date
            FROM data_bond_daily
            GROUP BY bond_code
        ) m ON d.bond_code = m.bond_code AND d.date = m.max_date
        WHERE d.close >= 120 AND d.close <= 250
    """, engine)
    print(f"  结果: {len(df2)} 条, 耗时: {time.time()-start:.2f}秒")
except Exception as e:
    print(f"  失败: {e}")

# 测试3：直接查询最新日期的数据
print("\n测试3：最新日期方式...")
start = time.time()
try:
    latest_date = pd.read_sql("SELECT MAX(date) as max_date FROM data_bond_daily", engine).iloc[0]['max_date']
    print(f"  最新日期: {latest_date}")
    df3 = pd.read_sql(f"""
        SELECT bond_code, close as bond_price, date as price_date
        FROM data_bond_daily
        WHERE date = '{latest_date}'
        AND close >= 120 AND close <= 250
    """, engine)
    print(f"  结果: {len(df3)} 条, 耗时: {time.time()-start:.2f}秒")
except Exception as e:
    print(f"  失败: {e}")
