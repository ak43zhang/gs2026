#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 analysis_news 相关表的 json_value 字段定义
"""
import pandas as pd
from sqlalchemy import create_engine

def check_json_value_column():
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    tables = [
        'analysis_news2026',
        'analysis_news2025',
        'analysis_news2024',
        'analysis_news_detail_2026',
        'analysis_news_combine2026',
        'analysis_news_combine2025',
        'analysis_notices2026',
        'analysis_notices2025',
        'analysis_notices2024'
    ]
    
    for table in tables:
        try:
            # 查看表结构
            df = pd.read_sql(f"SHOW COLUMNS FROM {table}", con=engine)
            json_row = df[df['Field'] == 'json_value']
            if not json_row.empty:
                print(f"\n{table}:")
                print(f"  Type: {json_row['Type'].values[0]}")
                print(f"  Null: {json_row['Null'].values[0]}")
                print(f"  Default: {json_row['Default'].values[0]}")
        except Exception as e:
            print(f"{table}: 查询失败 - {e}")

if __name__ == '__main__':
    check_json_value_column()
