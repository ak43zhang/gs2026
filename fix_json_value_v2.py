#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 json_value 字段空间不足问题
"""
from sqlalchemy import create_engine, text
import time

def fix_json_value():
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    tables_to_fix = [
        'analysis_news2026',
        'analysis_notices2026',
        'analysis_notices2025'
    ]
    
    with engine.connect() as conn:
        for table in tables_to_fix:
            try:
                sql = text(f'ALTER TABLE {table} MODIFY COLUMN json_value LONGTEXT')
                conn.execute(sql)
                conn.commit()
                print(f'{table}: json_value 已改为 LONGTEXT')
                time.sleep(0.5)  # 避免过快执行
            except Exception as e:
                print(f'{table}: 修改失败 - {e}')

if __name__ == '__main__':
    fix_json_value()
