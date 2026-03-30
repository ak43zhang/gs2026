#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MySQL 性能分析 - 简化版"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    print("=" * 70)
    print("MySQL 入库慢原因分析")
    print("=" * 70)
    
    # 1. 检查当前正在执行的查询
    print("\n【1】当前正在执行的慢查询:")
    result = conn.execute(text("""
        SELECT ID, TIME, STATE, LEFT(INFO, 60) as SQL_TEXT
        FROM INFORMATION_SCHEMA.PROCESSLIST
        WHERE COMMAND != 'Sleep' AND USER != 'system user' AND TIME > 0
        ORDER BY TIME DESC LIMIT 5
    """))
    
    has_slow = False
    for row in result:
        has_slow = True
        print(f"  ID={row[0]}, 已执行{row[1]}秒, 状态={row[2]}")
        print(f"    SQL: {row[3]}...")
    
    if not has_slow:
        print("  暂无执行中的查询")
    
    # 2. 检查 InnoDB 状态
    print("\n【2】InnoDB 关键指标:")
    result = conn.execute(text("SHOW ENGINE INNODB STATUS"))
    status = result.fetchone()[2]
    
    for line in status.split('\n'):
        if 'History list length' in line:
            print(f"  未清理事务: {line.strip()}")
        if 'Log sequence number' in line:
            print(f"  {line.strip()}")
        if 'Pending log writes' in line:
            print(f"  待写入日志: {line.strip()}")
        if 'Pending flushes' in line:
            print(f"  待刷新: {line.strip()}")
    
    # 3. 检查表状态
    print("\n【3】data_gpsj_day 表状态:")
    result = conn.execute(text("""
        SELECT 
            table_name,
            table_rows,
            ROUND(data_length/1024/1024, 1) as data_mb,
            ROUND(index_length/1024/1024, 1) as index_mb,
            ROUND(data_free/1024/1024, 1) as free_mb
        FROM information_schema.tables
        WHERE table_schema = 'gs' AND table_name LIKE 'data_gpsj_day_%'
        ORDER BY data_length DESC LIMIT 5
    """))
    
    for row in result:
        data_mb = float(row[2]) if row[2] else 0
        free_mb = float(row[4]) if row[4] else 0
        frag_pct = (free_mb / (data_mb + 0.01)) * 100
        print(f"  {row[0]}:")
        print(f"    行数: {row[1]}, 数据: {data_mb:.1f}MB, 索引: {float(row[3]):.1f}MB")
        print(f"    碎片: {free_mb:.1f}MB ({frag_pct:.1f}%)")
    
    # 4. 检查关键配置
    print("\n【4】关键配置参数:")
    params = [
        'innodb_buffer_pool_size',
        'innodb_log_file_size', 
        'innodb_flush_log_at_trx_commit',
        'max_allowed_packet',
        'innodb_flush_method'
    ]
    
    for param in params:
        try:
            result = conn.execute(text(f"SHOW VARIABLES LIKE '{param}'"))
            row = result.fetchone()
            if row:
                print(f"  {row[0]} = {row[1]}")
        except:
            pass
    
    # 5. 检查磁盘IO状态
    print("\n【5】InnoDB IO 统计:")
    result = conn.execute(text("""
        SHOW GLOBAL STATUS 
        WHERE Variable_name IN (
            'Innodb_data_reads', 'Innodb_data_writes',
            'Innodb_data_pending_reads', 'Innodb_data_pending_writes'
        )
    """))
    
    for row in result:
        print(f"  {row[0]} = {row[1]}")
    
    # 6. 检查是否有锁等待
    print("\n【6】锁等待情况:")
    result = conn.execute(text("""
        SHOW GLOBAL STATUS 
        WHERE Variable_name LIKE '%lock%wait%' OR Variable_name LIKE '%deadlock%'
    """))
    
    locks = list(result)
    if locks:
        for row in locks:
            print(f"  {row[0]} = {row[1]}")
    else:
        print("  暂无锁等待统计")
    
    print("\n" + "=" * 70)
