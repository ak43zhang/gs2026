#!/usr/bin/env python3
"""检查正股代码列"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import mysql_util
import pandas as pd

mysql_tool = mysql_util.get_mysql_tool()

# 检查两列的区别
with mysql_tool.engine.connect() as conn:
    df = pd.read_sql("""
        SELECT 
            `正股代码` as col4, 
            `正股代码2` as col12,
            `债券代码`,
            `债券名称`
        FROM data_bond_ths 
        LIMIT 10
    """, conn)
    print("对比两列正股代码:")
    print(df.to_string())
