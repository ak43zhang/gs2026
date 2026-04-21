#!/usr/bin/env python3
"""
表数据验证工具
验证特定表的数据完整性、一致性

使用示例:
    python tools/table_validator.py --table cache_stock_industry_concept_bond --check-bond
    python tools/table_validator.py --table data_bond_qs_jsl --check-expire
    python tools/table_validator.py --table data_industry_code_component_ths --stats
"""
import sys
sys.path.insert(0, 'src')

import argparse
import pandas as pd
from datetime import datetime
from gs2026.utils import mysql_util


def validate_bond_cache():
    """验证债券缓存表"""
    mysql_tool = mysql_util.get_mysql_tool()
    table = 'cache_stock_industry_concept_bond'
    
    print(f"\n=== 验证债券缓存表 ===")
    
    with mysql_tool.engine.connect() as conn:
        # 总记录数
        total = pd.read_sql(f"SELECT COUNT(*) as c FROM {table}", conn).iloc[0]['c']
        print(f"总股票数: {total}")
        
        # 有债券的股票
        with_bond = pd.read_sql(
            f"SELECT COUNT(*) as c FROM {table} WHERE bond_code IS NOT NULL AND bond_code != ''", 
            conn
        ).iloc[0]['c']
        print(f"有债券的股票: {with_bond} ({with_bond/total*100:.1f}%)")
        
        # 样本
        sample = pd.read_sql(
            f"SELECT stock_code, stock_name, bond_code, bond_name FROM {table} "
            f"WHERE bond_code IS NOT NULL LIMIT 5", 
            conn
        )
        print(f"\n样本:")
        for _, row in sample.iterrows():
            print(f"  {row['stock_code']} {row['stock_name']} -> {row['bond_code']} {row['bond_name']}")


def validate_bond_expire():
    """验证债券到期情况"""
    mysql_tool = mysql_util.get_mysql_tool()
    
    print(f"\n=== 验证债券到期情况 ===")
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    with mysql_tool.engine.connect() as conn:
        # data_bond_ths 表
        rows = pd.read_sql(
            f"SELECT COUNT(*) as total, "
            f"SUM(CASE WHEN `到期时间` < '{today}' THEN 1 ELSE 0 END) as expired "
            f"FROM data_bond_ths",
            conn
        ).iloc[0]
        print(f"data_bond_ths: 总计 {rows['total']}, 已到期 {rows['expired']}")
        
        # data_bond_qs_jsl 表
        rows = pd.read_sql(
            f"SELECT COUNT(*) as total FROM data_bond_qs_jsl",
            conn
        ).iloc[0]
        print(f"data_bond_qs_jsl: 总计 {rows['total']} (仅交易中)")


def validate_industry_component():
    """验证行业成分股表"""
    mysql_tool = mysql_util.get_mysql_tool()
    
    print(f"\n=== 验证行业成分股表 ===")
    
    with mysql_tool.engine.connect() as conn:
        # 行业数
        industries = pd.read_sql(
            "SELECT COUNT(DISTINCT code) as c FROM data_industry_code_component_ths",
            conn
        ).iloc[0]['c']
        print(f"行业数: {industries}")
        
        # 股票数
        stocks = pd.read_sql(
            "SELECT COUNT(DISTINCT stock_code) as c FROM data_industry_code_component_ths",
            conn
        ).iloc[0]['c']
        print(f"股票数: {stocks}")
        
        # 行业分布
        dist = pd.read_sql(
            "SELECT name, COUNT(*) as c FROM data_industry_code_component_ths "
            "GROUP BY name ORDER BY c DESC LIMIT 10",
            conn
        )
        print(f"\n前10大行业:")
        for _, row in dist.iterrows():
            print(f"  {row['name']}: {row['c']}只")


def main():
    parser = argparse.ArgumentParser(description='表数据验证工具')
    parser.add_argument('--table', help='指定表名')
    parser.add_argument('--check-bond', action='store_true', help='验证债券缓存')
    parser.add_argument('--check-expire', action='store_true', help='检查债券到期')
    parser.add_argument('--check-industry', action='store_true', help='验证行业成分股')
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    
    args = parser.parse_args()
    
    if args.check_bond:
        validate_bond_cache()
    elif args.check_expire:
        validate_bond_expire()
    elif args.check_industry:
        validate_industry_component()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
