#!/usr/bin/env python3
"""检查概念代码匹配"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

# 获取概念名称表的代码
with mysql_tool.engine.connect() as conn:
    gn_df = pd.read_sql('SELECT code FROM ths_gn_names LIMIT 10', conn)
    print('ths_gn_names 中的code示例:')
    print(gn_df['code'].tolist())

# 获取成分股表的概念代码
with mysql_tool.engine.connect() as conn:
    cf_df = pd.read_sql('SELECT DISTINCT index_code FROM data_gnzscfxx_ths LIMIT 10', conn)
    print('\ndata_gnzscfxx_ths 中的index_code示例:')
    print(cf_df['index_code'].tolist())
