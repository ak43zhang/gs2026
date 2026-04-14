#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为今天的监控表添加索引 - 使用SQLAlchemy
实施方案A: 立即添加（Online DDL）
"""
import time
from datetime import datetime
from sqlalchemy import create_engine, text
from loguru import logger
from gs2026.utils import config_util

# 创建连接
url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

date_str = '20260331'

# 索引配置（按表分组）
INDEX_CONFIG = [
    # 小表（先添加）
    {
        'table': f'monitor_gp_top30_{date_str}',
        'indexes': ['ADD INDEX idx_time (time)']
    },
    {
        'table': f'monitor_zq_top30_{date_str}',
        'indexes': ['ADD INDEX idx_time (time)']
    },
    {
        'table': f'monitor_hy_top30_{date_str}',
        'indexes': ['ADD INDEX idx_time (time)']
    },
    {
        'table': f'monitor_gp_apqd_{date_str}',
        'indexes': ['ADD INDEX idx_time (time)']
    },
    # 中等表
    {
        'table': f'monitor_hy_sssj_{date_str}',
        'indexes': [
            'ADD INDEX idx_code_time (industry_code, time)',
            'ADD INDEX idx_time (time)'
        ]
    },
    {
        'table': f'monitor_zq_sssj_{date_str}',
        'indexes': [
            'ADD INDEX idx_code_time (bond_code, time)',
            'ADD INDEX idx_time (time)'
        ]
    },
    # 大表（最后添加）
    {
        'table': f'monitor_gp_sssj_{date_str}',
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

with engine.connect() as conn:
    for config in INDEX_CONFIG:
        table_name = config['table']
        print(f'\n[{table_name}]')
        
        # 检查表是否存在
        try:
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.TABLES 
                WHERE table_schema = DATABASE() AND table_name = '{table_name}'
            """))
            exists = result.scalar() > 0
            
            if not exists:
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
                print(f'  执行: {index_sql}')
                
                idx_start = time.time()
                conn.execute(text(f"ALTER TABLE {table_name} {index_sql}"))
                conn.commit()
                idx_time = time.time() - idx_start
                
                print(f'  [OK] 成功 ({idx_time:.2f}s)')
                success_count += 1
                
            except Exception as e:
                error_msg = str(e)
                if 'Duplicate' in error_msg or 'already exists' in error_msg:
                    print(f'  [WARN] 索引已存在，跳过')
                    success_count += 1  # 也算成功
                else:
                    print(f'  [FAIL] 失败: {e}')
        
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
        print(f'  [OK] {r["table"]} ({r["indexes_added"]} 个索引, {r["time"]}s)')

if failed_tables:
    print('\n失败的表:')
    for r in failed_tables:
        print(f'  [FAIL] {r["table"]}: {r.get("reason", "未知错误")}')

print('\n' + '=' * 70)
print('索引添加完成！')
print(f'结束时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 70)

# 验证索引
print('\n验证索引...')
with engine.connect() as conn:
    for config in INDEX_CONFIG[:3]:  # 只验证前3个表
        table_name = config['table']
        try:
            result = conn.execute(text(f"""
                SELECT index_name, column_name 
                FROM information_schema.STATISTICS 
                WHERE table_schema = DATABASE() 
                AND table_name = '{table_name}'
                AND index_name != 'PRIMARY'
            """))
            rows = result.fetchall()
            if rows:
                print(f'{table_name}:')
                for row in rows:
                    print(f'  - {row[0]}: {row[1]}')
            else:
                print(f'{table_name}: 无索引')
        except Exception as e:
            print(f'{table_name}: 验证失败 - {e}')

engine.dispose()
print('\n完成！')
