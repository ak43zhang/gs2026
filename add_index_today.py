#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为今天的监控表添加索引
实施方案A: 立即添加（Online DDL）
"""
import time
from datetime import datetime
from loguru import logger

from gs2026.utils import mysql_util

mysql_tool = mysql_util.MysqlTool()

date_str = '20260331'

# 索引配置
INDEX_CONFIG = [
    # 小表（先添加）
    {
        'name': 'monitor_gp_top30',
        'indexes': ['ADD INDEX idx_time (time)']
    },
    {
        'name': 'monitor_zq_top30',
        'indexes': ['ADD INDEX idx_time (time)']
    },
    {
        'name': 'monitor_hy_top30',
        'indexes': ['ADD INDEX idx_time (time)']
    },
    {
        'name': 'monitor_gp_apqd',
        'indexes': ['ADD INDEX idx_time (time)']
    },
    # 中等表
    {
        'name': 'monitor_hy_sssj',
        'indexes': [
            'ADD INDEX idx_code_time (industry_code, time)',
            'ADD INDEX idx_time (time)'
        ]
    },
    {
        'name': 'monitor_zq_sssj',
        'indexes': [
            'ADD INDEX idx_code_time (bond_code, time)',
            'ADD INDEX idx_time (time)'
        ]
    },
    # 大表（最后添加）
    {
        'name': 'monitor_gp_sssj',
        'indexes': [
            'ADD INDEX idx_code_time (stock_code, time)',
            'ADD INDEX idx_time (time)'
        ]
    },
]

print('=' * 70)
print(f'为 {date_str} 的监控表添加索引')
print(f'开始时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 70)

total_start = time.time()
results = []

for config in INDEX_CONFIG:
    table_name = f"{config['name']}_{date_str}"
    print(f'\n【{table_name}】')
    
    # 检查表是否存在
    try:
        result = mysql_tool.query(f"""
            SELECT COUNT(*) FROM information_schema.TABLES 
            WHERE table_schema = DATABASE() AND table_name = '{table_name}'
        """)
        if not result or result[0][0] == 0:
            print('  状态: 表不存在，跳过')
            results.append({'table': table_name, 'status': 'skipped', 'reason': '表不存在'})
            continue
    except Exception as e:
        print(f'  检查表失败: {e}')
        results.append({'table': table_name, 'status': 'error', 'reason': str(e)})
        continue
    
    # 添加索引
    table_start = time.time()
    success_count = 0
    
    for index_sql in config['indexes']:
        try:
            sql = f"ALTER TABLE {table_name} {index_sql}"
            print(f'  执行: {index_sql}')
            
            # 使用ALGORITHM=INPLACE, LOCK=NONE确保Online DDL
            sql_online = f"ALTER TABLE {table_name} {index_sql}, ALGORITHM=INPLACE, LOCK=NONE"
            
            idx_start = time.time()
            mysql_tool.execute(sql_online)
            idx_time = time.time() - idx_start
            
            print(f'  ✓ 成功 ({idx_time:.2f}s)')
            success_count += 1
            
        except Exception as e:
            error_msg = str(e)
            # 如果Online DDL不支持，尝试普通方式
            if 'ALGORITHM' in error_msg or 'LOCK' in error_msg:
                try:
                    print(f'  Online DDL不支持，尝试普通方式...')
                    mysql_tool.execute(sql)
                    print(f'  ✓ 成功（普通方式）')
                    success_count += 1
                except Exception as e2:
                    print(f'  ✗ 失败: {e2}')
            else:
                print(f'  ✗ 失败: {e}')
    
    table_time = time.time() - table_start
    results.append({
        'table': table_name,
        'status': 'success' if success_count > 0 else 'failed',
        'indexes_added': success_count,
        'time': round(table_time, 2)
    })
    print(f'  耗时: {table_time:.2f}s')

total_time = time.time() - total_start

# 汇总
print('\n' + '=' * 70)
print('执行汇总')
print('=' * 70)

success_tables = [r for r in results if r['status'] == 'success']
skipped_tables = [r for r in results if r['status'] == 'skipped']
failed_tables = [r for r in results if r['status'] == 'failed']

print(f'\n总耗时: {total_time:.2f}s')
print(f'成功: {len(success_tables)} 个表')
print(f'跳过: {len(skipped_tables)} 个表')
print(f'失败: {len(failed_tables)} 个表')

if success_tables:
    print('\n成功添加索引的表:')
    for r in success_tables:
        print(f'  ✓ {r["table"]} ({r["indexes_added"]} 个索引, {r["time"]}s)')

if failed_tables:
    print('\n失败的表:')
    for r in failed_tables:
        print(f'  ✗ {r["table"]}: {r.get("reason", "未知错误")}')

print('\n' + '=' * 70)
print('索引添加完成！')
print(f'结束时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 70)

# 验证索引
print('\n验证索引...')
for config in INDEX_CONFIG[:3]:  # 只验证前3个表
    table_name = f"{config['name']}_{date_str}"
    try:
        result = mysql_tool.query(f"""
            SELECT index_name, column_name 
            FROM information_schema.STATISTICS 
            WHERE table_schema = DATABASE() 
            AND table_name = '{table_name}'
            AND index_name != 'PRIMARY'
        """)
        if result:
            print(f'{table_name}:')
            for row in result:
                print(f'  - {row[0]}: {row[1]}')
    except Exception as e:
        print(f'{table_name}: 验证失败 - {e}')
