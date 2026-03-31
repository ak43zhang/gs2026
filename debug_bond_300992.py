#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排查 300992 - 123160 债券关联问题
"""
import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    print('=' * 60)
    print('排查 300992 - 123160 债券关联问题')
    print('=' * 60)
    
    # 1. 检查行业表
    result = conn.execute(text("SELECT stock_code, short_name FROM data_industry_code_component_ths WHERE stock_code = '300992'")).fetchone()
    print(f'\n1. 行业成分股表: {result if result else "无记录"}')
    
    # 2. 检查债券基础信息
    result = conn.execute(text("SELECT `债券代码`, `债券简称`, `正股代码`, `上市日期`, `申购日期` FROM data_bond_ths WHERE `债券代码` = '123160'")).fetchone()
    print(f'\n2. 债券基础信息: {result if result else "无记录"}')
    
    # 3. 检查债券价格
    result = conn.execute(text("SELECT bond_code, close, date FROM data_bond_daily WHERE bond_code = '123160' ORDER BY date DESC LIMIT 1")).fetchone()
    print(f'\n3. 债券最新价格: {result if result else "无记录"}')
    if result:
        close_price = result[1]
        if close_price < 120:
            print(f'   价格 {close_price} 低于下限 120，被过滤！')
        elif close_price > 250:
            print(f'   价格 {close_price} 高于上限 250，被过滤！')
        else:
            print(f'   价格 {close_price} 在正常范围')
    
    # 4. 检查完整关联
    result = conn.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT b.`债券代码`, b.`正股代码`, p.close
            FROM data_bond_ths b
            JOIN data_bond_daily p ON b.`债券代码` = p.bond_code
            WHERE b.`债券代码` = '123160'
            AND p.date = (SELECT MAX(date) FROM data_bond_daily)
            AND p.close >= 120 AND p.close <= 250
        ) t
    """)).fetchone()
    print(f'\n4. 关联后记录数: {result[0]} {"存在" if result[0] > 0 else "被过滤"}')

print('\n' + '=' * 60)
print('排查完成')
print('=' * 60)
