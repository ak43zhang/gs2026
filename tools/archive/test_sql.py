#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""直接测试SQL查询"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine

# 连接数据库
url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs"
engine = create_engine(url)

# 测试查询
import pandas as pd
sql = """
    SELECT COUNT(*) as total 
    FROM analysis_ztb_detail_2026 
    WHERE trade_date = '2026-04-13'
"""
df = pd.read_sql(sql, engine)
print(f"Total records: {df.iloc[0]['total']}")

# 查询具体数据
sql2 = """
    SELECT content_hash, stock_name, stock_code, zt_time, zt_time_range
    FROM analysis_ztb_detail_2026 
    WHERE trade_date = '2026-04-13'
    LIMIT 3
"""
df2 = pd.read_sql(sql2, engine)
print(f"\nSample data:")
print(df2.to_string())
