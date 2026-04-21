#!/usr/bin/env python3
"""检查行业代码表"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd
from sqlalchemy import text

mysql_tool = mysql_util.get_mysql_tool()

print("=== data_industry_code_ths 表（行业名称表） ===")
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql(text("SELECT code, name FROM data_industry_code_ths"), conn)
    # 显示包含电力或化学的行
    mask = df['name'].str.contains('电力|化学', na=False)
    print(df[mask].to_string())

print("\n=== data_industry_code_component_ths 表（行业成分股表） ===")
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql(text("SELECT DISTINCT code, name FROM data_industry_code_component_ths"), conn)
    # 显示包含电力或化学的行
    mask = df['name'].str.contains('电力|化学', na=False)
    print(df[mask].to_string())
