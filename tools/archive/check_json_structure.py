#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""查看涨停分析JSON字段结构"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine
import pandas as pd
import json

# 连接数据库
url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs"
engine = create_engine(url)

# 查询一条记录
sql = """
    SELECT stock_code, stock_name, 
           sector_msg, concept_msg, leading_stock_msg, 
           influence_msg, expect_msg, deep_analysis
    FROM analysis_ztb_detail_2026 
    WHERE trade_date = '2026-04-13' 
    LIMIT 1
"""
df = pd.read_sql(sql, engine)

if not df.empty:
    row = df.iloc[0]
    print(f"股票: {row['stock_name']} ({row['stock_code']})")
    print("\n" + "="*60)
    
    fields = ['sector_msg', 'concept_msg', 'leading_stock_msg', 
              'influence_msg', 'expect_msg', 'deep_analysis']
    
    for field in fields:
        print(f"\n【{field}】")
        try:
            data = json.loads(row[field]) if row[field] else []
            print(f"类型: {type(data)}")
            if isinstance(data, list) and len(data) > 0:
                print(f"数量: {len(data)}")
                print(f"第一条结构:")
                print(json.dumps(data[0], ensure_ascii=False, indent=2))
            elif isinstance(data, list):
                print("空列表")
            else:
                print(f"数据: {data}")
        except Exception as e:
            print(f"解析错误: {e}")
            print(f"原始数据: {row[field]}")
