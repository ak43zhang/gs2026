#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import config_util

url = config_util.get_config('common.url')
print(f"Original URL: {url}")

# 修复URL
if 'charset=' not in url:
    url += '?charset=utf8mb4'
elif 'charset=utf8&' in url:
    url = url.replace('charset=utf8&', 'charset=utf8mb4&')
elif 'charset=utf8' in url and 'charset=utf8mb4' not in url:
    url = url.replace('charset=utf8', 'charset=utf8mb4')

print(f"Fixed URL: {url}")

from sqlalchemy import create_engine, event
import pandas as pd

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

@event.listens_for(engine, "connect")
def set_utf8mb4(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET NAMES utf8mb4")
    cursor.close()

sql = "SELECT stock_code, stock_name FROM analysis_ztb_detail_2026 WHERE trade_date = '2026-04-13' LIMIT 3"
df = pd.read_sql(sql, engine)
print(f"\nDataFrame:")
print(df)
print(f"\nFirst row stock_name: {df.iloc[0]['stock_name']}")
