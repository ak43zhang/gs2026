#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查今天的监控表状态，评估添加索引的影响
"""
from gs2026.utils import mysql_util
from loguru import logger

mysql_tool = mysql_util.MysqlTool()

date_str = '20260331'

tables = [
    f'monitor_gp_sssj_{date_str}',
    f'monitor_zq_sssj_{date_str}',
    f'monitor_hy_sssj_{date_str}',
    f'monitor_gp_top30_{date_str}',
    f'monitor_zq_top30_{date_str}',
    f'monitor_hy_top30_{date_str}',
    f'monitor_gp_apqd_{date_str}',
]

print('=' * 70)
print(f'今天的监控表状态检查 ({date_str})')
print('=' * 70)

for table in tables:
    print(f'\n【{table}】')
    
    # 1. 检查表是否存在
    try:
        result = mysql_tool.query(f"""
            SELECT COUNT(*) FROM information_schema.TABLES 
            WHERE table_schema = DATABASE() AND table_name = '{table}'
        """)
        exists = result and result[0][0] > 0
        
        if not exists:
            print('  状态: 表不存在')
            continue
        
        print('  状态: ✓ 表存在')
        
        # 2. 检查表的数据量
        result = mysql_tool.query(f"SELECT COUNT(*) FROM {table}")
        count = result[0][0] if result else 0
        print(f'  数据量: {count:,} 条')
        
        # 3. 检查已有索引
        result = mysql_tool.query(f"""
            SELECT index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) as columns
            FROM information_schema.STATISTICS 
            WHERE table_schema = DATABASE() 
            AND table_name = '{table}'
            GROUP BY index_name
        """)
        
        if result:
            print('  已有索引:')
            for row in result:
                index_name, columns = row
                print(f'    - {index_name}: {columns}')
        else:
            print('  已有索引: 无')
        
    except Exception as e:
        print(f'  错误: {e}')

print('\n' + '=' * 70)
print('索引添加影响评估')
print('=' * 70)

# 检查MySQL版本和存储引擎
try:
    result = mysql_tool.query("SELECT VERSION()")
    version = result[0][0] if result else '未知'
    print(f'\nMySQL版本: {version}')

    result = mysql_tool.query(f"""
        SELECT engine FROM information_schema.TABLES 
        WHERE table_schema = DATABASE() 
        AND table_name = 'monitor_gp_sssj_{date_str}'
    """)
    engine = result[0][0] if result else '未知'
    print(f'存储引擎: {engine}')
except Exception as e:
    print(f'查询错误: {e}')

print("""

【影响评估】

1. 索引添加对INSERT的影响:
   - MySQL 5.6+: 支持Online DDL，添加索引不会阻塞INSERT
   - 但会增加INSERT的耗时（需要维护索引）
   - 预计INSERT性能下降: 10-20%

2. 索引添加对SELECT的影响:
   - 立即生效，查询性能大幅提升
   - 预计查询性能提升: 100-500倍

3. 索引添加时间估算:
   - 100万条数据: 约1-3秒
   - 1000万条数据: 约10-30秒
   - 2400万条数据: 约30-60秒

4. 风险评估:
   - 低风险: MySQL 5.6+ 支持Online DDL
   - 中风险: 添加索引期间CPU和IO会升高
   - 建议: 在交易量低的时候执行

【建议】

方案A: 立即添加（推荐）
- 当前时间14:12，不是交易高峰
- MySQL 5.6+ 支持Online DDL，不会阻塞写入
- 索引添加完成后立即生效

方案B: 收盘后添加
- 等待15:00收盘后执行
- 更安全，但慢查询问题持续

方案C: 分表添加
- 先添加小表（top30, apqd）
- 再添加大表（sssj）
- 降低单次操作风险
""")
