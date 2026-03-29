#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试查询 - 包含赎回日期"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

import pandas as pd
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 测试查询 - 包含中签率公布日期
try:
    df = pd.read_sql("""
        SELECT 
            `债券代码`,
            `债券简称`,
            `正股代码`,
            `正股简称`,
            `转股价格`,
            `上市日期`,
            `中签率公布日期`
        FROM data_bond_ths
        LIMIT 3
    """, engine)
    print("查询成功!")
    print(df)
except Exception as e:
    print(f"查询失败: {e}")
    
# 测试查询 - 使用正确的字段名
try:
    df = pd.read_sql("""
        SELECT 
            `债券代码`,
            `债券简称`,
            `正股代码`,
            `正股简称`,
            `转股价格`,
            `上市日期`,
            `申购日期`
        FROM data_bond_ths
        LIMIT 3
    """, engine)
    print("\n使用申购日期查询成功!")
    print(df)
except Exception as e:
    print(f"\n使用申购日期查询失败: {e}")
