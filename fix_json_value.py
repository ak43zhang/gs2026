#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 json_value 字段空间不足问题
"""
import pymysql

def fix_json_value():
    conn = pymysql.connect(
        host='192.168.0.101',
        port=3306,
        user='root',
        password='123456',
        database='gs',
        charset='utf8mb4'
    )
    
    tables_to_fix = [
        'analysis_news2026',
        'analysis_notices2026',
        'analysis_notices2025'
    ]
    
    try:
        with conn.cursor() as cursor:
            for table in tables_to_fix:
                try:
                    sql = f'ALTER TABLE {table} MODIFY COLUMN json_value LONGTEXT'
                    cursor.execute(sql)
                    conn.commit()
                    print(f'{table}: json_value 已改为 LONGTEXT')
                except Exception as e:
                    print(f'{table}: 修改失败 - {e}')
    finally:
        conn.close()

if __name__ == '__main__':
    fix_json_value()
