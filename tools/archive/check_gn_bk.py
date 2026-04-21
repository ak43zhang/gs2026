#!/usr/bin/env python3
"""检查ths_gn_bk表"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

# 检查ths_gn_bk表
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql('SELECT DISTINCT code, name FROM ths_gn_bk LIMIT 10', conn)
    print('ths_gn_bk 表概念代码和名称:')
    print(df.to_string())
    
# 检查data_gnzscfxx_ths的概念代码是否在ths_gn_bk中
with mysql_tool.engine.connect() as conn:
    df1 = pd.read_sql('SELECT DISTINCT index_code FROM data_gnzscfxx_ths LIMIT 10', conn)
    print('\ndata_gnzscfxx_ths 的概念代码:')
    codes1 = set(df1['index_code'].tolist())
    print(codes1)
    
with mysql_tool.engine.connect() as conn:
    df2 = pd.read_sql('SELECT DISTINCT code FROM ths_gn_bk', conn)
    codes2 = set(df2['code'].tolist())
    
print(f'\n交集数量: {len(codes1 & codes2)}')
print(f'只在data_gnzscfxx_ths中的代码: {codes1 - codes2}')
