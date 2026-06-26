#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查表数据量
"""
from sqlalchemy import create_engine, text

def check_table_size():
    db_url = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
    engine = create_engine(db_url)
    
    tables = [
        'analysis_news2026',
        'analysis_notices2026',
        'analysis_notices2025'
    ]
    
    with engine.connect() as conn:
        for table in tables:
            try:
                result = conn.execute(text(f'SELECT COUNT(*) FROM {table}'))
                count = result.scalar()
                print(f'{table}: {count} 行')
            except Exception as e:
                print(f'{table}: 查询失败 - {e}')

if __name__ == '__main__':
    check_table_size()
