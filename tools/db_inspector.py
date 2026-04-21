#!/usr/bin/env python3
"""
数据库诊断工具
检查表结构、字段、索引、数据量等

使用示例:
    python tools/db_inspector.py --table monitor_gp_sssj_20260421
    python tools/db_inspector.py --pattern "monitor_%" --check-index
    python tools/db_inspector.py --all-tables
"""
import sys
sys.path.insert(0, 'src')

import argparse
import pandas as pd
from sqlalchemy import text
from gs2026.utils import mysql_util


def check_table_structure(table_name: str):
    """检查表结构"""
    mysql_tool = mysql_util.get_mysql_tool()
    
    print(f"\n=== 表结构: {table_name} ===")
    
    with mysql_tool.engine.connect() as conn:
        # 字段信息
        columns = pd.read_sql(f"SHOW COLUMNS FROM {table_name}", conn)
        print(f"\n字段数: {len(columns)}")
        for _, row in columns.iterrows():
            print(f"  {row['Field']}: {row['Type']}")
        
        # 索引信息
        indexes = pd.read_sql(f"SHOW INDEX FROM {table_name}", conn)
        print(f"\n索引数: {len(indexes)}")
        for _, row in indexes.iterrows():
            print(f"  {row['Key_name']}: {row['Column_name']} ({row['Index_type']})")
        
        # 数据量
        count = pd.read_sql(f"SELECT COUNT(*) as c FROM {table_name}", conn).iloc[0]['c']
        print(f"\n数据量: {count}")
        
        # 样本数据
        sample = pd.read_sql(f"SELECT * FROM {table_name} LIMIT 3", conn)
        print(f"\n样本数据:")
        print(sample.to_string())


def check_tables_by_pattern(pattern: str, check_index: bool = False):
    """按模式检查多个表"""
    mysql_tool = mysql_util.get_mysql_tool()
    
    print(f"\n=== 匹配模式: {pattern} ===")
    
    with mysql_tool.engine.connect() as conn:
        tables = pd.read_sql(f"SHOW TABLES LIKE '{pattern}'", conn)
        table_list = tables.iloc[:, 0].tolist()
    
    print(f"找到 {len(table_list)} 个表")
    
    for table in table_list:
        with mysql_tool.engine.connect() as conn:
            count = pd.read_sql(f"SELECT COUNT(*) as c FROM {table}", conn).iloc[0]['c']
            print(f"  {table}: {count} 条记录")
            
            if check_index:
                indexes = pd.read_sql(f"SHOW INDEX FROM {table}", conn)
                print(f"    索引: {', '.join(indexes['Key_name'].unique())}")


def main():
    parser = argparse.ArgumentParser(description='数据库诊断工具')
    parser.add_argument('--table', help='检查指定表')
    parser.add_argument('--pattern', help='按模式匹配表')
    parser.add_argument('--check-index', action='store_true', help='同时检查索引')
    parser.add_argument('--all-tables', action='store_true', help='列出所有表')
    
    args = parser.parse_args()
    
    if args.table:
        check_table_structure(args.table)
    elif args.pattern:
        check_tables_by_pattern(args.pattern, args.check_index)
    elif args.all_tables:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            tables = pd.read_sql("SHOW TABLES", conn)
            print(f"\n数据库共有 {len(tables)} 个表:")
            for t in tables.iloc[:, 0].tolist():
                print(f"  {t}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
