#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票-债券-行业 映射关系生成器
生成 1对1对1 关系的 DataFrame
"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from gs2026.utils.mysql_util import mysql_tool


def get_stock_bond_industry_mapping():
    """
    获取股票、债券、行业的 1对1对1 映射关系
    
    Returns:
        DataFrame: 包含 stock_code, short_name, bond_code, bond_name, industry_name
    """
    # 读取行业成分股数据
    print("读取行业成分股数据...")
    df_industry = mysql_tool.query_to_dataframe('''
        SELECT DISTINCT
            stock_code, 
            short_name, 
            name AS industry_name 
        FROM data_industry_code_component_ths
        WHERE stock_code IS NOT NULL 
          AND stock_code != ''
        ORDER BY stock_code
    ''')
    print(f"行业成分股数据: {len(df_industry)} 条")
    
    # 读取债券数据
    print("读取债券数据...")
    df_bond = mysql_tool.query_to_dataframe('''
        SELECT DISTINCT
            bond_code, 
            bond_name, 
            stock_code 
        FROM data_bond_ths
        WHERE stock_code IS NOT NULL 
          AND stock_code != ''
          AND bond_code IS NOT NULL
          AND bond_code != ''
        ORDER BY stock_code
    ''')
    print(f"债券数据: {len(df_bond)} 条")
    
    # 合并数据（1对1对1关系）
    print("合并数据...")
    df_result = pd.merge(
        df_industry, 
        df_bond, 
        on='stock_code', 
        how='inner'  # 只保留两边都有的记录，确保 1对1对1 关系
    )
    
    # 去重（如果有多条记录，保留第一条）
    df_result = df_result.drop_duplicates(subset=['stock_code'], keep='first')
    
    # 选择需要的列并重命名
    df_result = df_result[[
        'stock_code', 
        'short_name', 
        'bond_code', 
        'bond_name', 
        'industry_name'
    ]]
    
    print(f"\n映射结果: {len(df_result)} 条记录")
    print(f"列: {list(df_result.columns)}")
    
    return df_result


def get_mapping_with_left_join():
    """
    使用 LEFT JOIN 获取映射关系（包含无债券的股票）
    
    Returns:
        DataFrame: 包含所有股票，债券可能为 NULL
    """
    print("读取行业成分股数据...")
    df_industry = mysql_tool.query_to_dataframe('''
        SELECT DISTINCT
            stock_code, 
            short_name, 
            name AS industry_name 
        FROM data_industry_code_component_ths
        WHERE stock_code IS NOT NULL 
          AND stock_code != ''
        ORDER BY stock_code
    ''')
    
    print("读取债券数据...")
    df_bond = mysql_tool.query_to_dataframe('''
        SELECT DISTINCT
            bond_code, 
            bond_name, 
            stock_code 
        FROM data_bond_ths
        WHERE stock_code IS NOT NULL 
          AND stock_code != ''
          AND bond_code IS NOT NULL
          AND bond_code != ''
        ORDER BY stock_code
    ''')
    
    print("合并数据 (LEFT JOIN)...")
    df_result = pd.merge(
        df_industry, 
        df_bond, 
        on='stock_code', 
        how='left'  # 保留所有股票，即使无对应债券
    )
    
    # 去重
    df_result = df_result.drop_duplicates(subset=['stock_code'], keep='first')
    
    # 选择需要的列
    df_result = df_result[[
        'stock_code', 
        'short_name', 
        'bond_code', 
        'bond_name', 
        'industry_name'
    ]]
    
    # 统计
    total = len(df_result)
    with_bond = df_result['bond_code'].notna().sum()
    without_bond = total - with_bond
    
    print(f"\n映射结果: {total} 条记录")
    print(f"  - 有债券: {with_bond} 条")
    print(f"  - 无债券: {without_bond} 条")
    
    return df_result


def save_mapping_to_csv(df, filepath='stock_bond_industry_mapping.csv'):
    """保存映射关系到 CSV 文件"""
    df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f"\n已保存到: {filepath}")


def save_mapping_to_mysql(df, table_name='stock_bond_industry_mapping'):
    """保存映射关系到 MySQL 表"""
    print(f"\n保存到 MySQL 表: {table_name}")
    
    # 先删除旧表
    mysql_tool.execute(f'DROP TABLE IF EXISTS {table_name}')
    
    # 创建新表
    create_sql = f'''
    CREATE TABLE {table_name} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
        short_name VARCHAR(100) COMMENT '股票简称',
        bond_code VARCHAR(20) COMMENT '债券代码',
        bond_name VARCHAR(100) COMMENT '债券简称',
        industry_name VARCHAR(100) COMMENT '行业名称',
        create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_stock_code (stock_code),
        INDEX idx_bond_code (bond_code),
        INDEX idx_industry (industry_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票-债券-行业映射关系表'
    '''
    mysql_tool.execute(create_sql)
    
    # 插入数据
    mysql_tool.dataframe_to_mysql(df, table_name)
    print(f"已插入 {len(df)} 条记录")


if __name__ == '__main__':
    # 获取 1对1对1 映射关系
    print("=" * 60)
    print("股票-债券-行业 1对1对1 映射关系生成")
    print("=" * 60)
    
    # 方法1: INNER JOIN（只保留有债券的股票）
    print("\n【方法1】INNER JOIN - 只保留有债券的股票")
    df_mapping = get_stock_bond_industry_mapping()
    print("\n前10条记录:")
    print(df_mapping.head(10).to_string())
    
    # 保存到 CSV
    save_mapping_to_csv(df_mapping, 'stock_bond_industry_mapping.csv')
    
    # 方法2: LEFT JOIN（保留所有股票）
    print("\n" + "=" * 60)
    print("【方法2】LEFT JOIN - 保留所有股票")
    df_mapping_all = get_mapping_with_left_join()
    
    # 保存到 CSV
    save_mapping_to_csv(df_mapping_all, 'stock_bond_industry_mapping_all.csv')
    
    # 可选: 保存到 MySQL
    # save_mapping_to_mysql(df_mapping)
    
    print("\n" + "=" * 60)
    print("完成!")
    print("=" * 60)
