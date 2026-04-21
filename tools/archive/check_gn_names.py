#!/usr/bin/env python3
"""检查概念名称表"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SELECT * FROM ths_gn_names LIMIT 5', conn)
    print(df.to_string())
    
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SELECT COUNT(*) as c FROM ths_gn_names', conn)
    print(f'\n总行数: {df.iloc[0]["c"]}')
