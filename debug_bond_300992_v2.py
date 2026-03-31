#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
进一步排查 300992 - 123160 关联问题
"""
import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    print('=' * 60)
    print('进一步排查关联问题')
    print('=' * 60)
    
    # 获取最新日期
    result = conn.execute(text("SELECT MAX(date) FROM data_bond_daily")).fetchone()
    latest_date = result[0]
    print(f'\n债券日行情最新日期: {latest_date}')
    
    # 检查123160在最新日期的价格
    result = conn.execute(text(f"SELECT bond_code, close FROM data_bond_daily WHERE bond_code = '123160' AND date = '{latest_date}'")).fetchone()
    print(f'123160在{latest_date}的价格: {result if result else "无记录"}')
    
    # 检查123160在2026-03-23的价格（有数据的日期）
    result = conn.execute(text("SELECT bond_code, close, date FROM data_bond_daily WHERE bond_code = '123160' AND date = '2026-03-23'")).fetchone()
    print(f'123160在2026-03-23的价格: {result if result else "无记录"}')
    
    # 检查data_bond_ths中的正股代码格式
    result = conn.execute(text("SELECT `债券代码`, `正股代码`, LENGTH(`正股代码`) as code_len FROM data_bond_ths WHERE `债券代码` = '123160'")).fetchone()
    print(f'\n债券123160的正股代码: {result}')
    
    # 检查data_industry_code_component_ths中的stock_code格式
    result = conn.execute(text("SELECT stock_code, LENGTH(stock_code) as code_len FROM data_industry_code_component_ths WHERE stock_code = '300992'")).fetchone()
    print(f'行业表中的300992: {result}')
    
    # 检查是否有空格问题
    result = conn.execute(text("SELECT `正股代码`, TRIM(`正股代码`) as trimmed FROM data_bond_ths WHERE `债券代码` = '123160'")).fetchone()
    print(f'\n正股代码是否有空格: {result}')
    
    # 尝试直接关联查询
    result = conn.execute(text("""
        SELECT 
            i.stock_code as industry_stock,
            b.`正股代码` as bond_stock,
            i.stock_code = b.`正股代码` as is_equal,
            i.stock_code = TRIM(b.`正股代码`) as is_equal_trimmed
        FROM data_industry_code_component_ths i
        LEFT JOIN data_bond_ths b ON i.stock_code = b.`正股代码`
        WHERE i.stock_code = '300992' AND b.`债券代码` = '123160'
    """)).fetchone()
    print(f'\n直接关联结果: {result if result else "无关联"}')

print('\n' + '=' * 60)
print('排查完成')
print('=' * 60)
