#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MySQL 性能分析 - 入库慢原因排查"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    print("=" * 70)
    print("MySQL 入库性能分析")
    print("=" * 70)
    
    # 1. 检查当前正在执行的慢查询
    print("\n【1】当前正在执行的查询（按时间排序）:")
    result = conn.execute(text("""
        SELECT 
            ID,
            USER,
            HOST,
            DB,
            COMMAND,
            TIME,
            STATE,
            LEFT(INFO, 80) as INFO
        FROM INFORMATION_SCHEMA.PROCESSLIST
        WHERE COMMAND != 'Sleep'
          AND USER != 'system user'
        ORDER BY TIME DESC
        LIMIT 10
    """))
    
    for row in result:
        print(f"  ID={row[0]}, TIME={row[5]}s, STATE={row[6]}")
        print(f"    SQL: {row[7]}...")
    
    # 2. 检查 InnoDB 状态
    print("\n【2】InnoDB 事务状态:")
    result = conn.execute(text("SHOW ENGINE INNODB STATUS"))
    status = result.fetchone()[2]
    
    # 提取关键信息
    for line in status.split('\n'):
        if 'History list length' in line:
            print(f"  历史列表长度: {line.strip()}")
        if 'Log sequence number' in line:
            print(f"  {line.strip()}")
        if 'Pending log writes' in line:
            print(f"  {line.strip()}")
    
    # 3. 检查表锁情况
    print("\n【3】表锁等待情况:")
    result = conn.execute(text("""
        SELECT 
            r.object_schema,
            r.object_name,
            r.thread_id AS waiting_thread,
            r.processlist_id AS waiting_pid,
            b.thread_id AS blocking_thread,
            b.processlist_id AS blocking_pid,
            r.lock_type AS waiting_lock,
            r.lock_duration AS waiting_duration,
            b.lock_type AS blocking_lock,
            b.lock_duration AS blocking_duration
        FROM performance_schema.metadata_locks r
        JOIN performance_schema.metadata_locks b ON r.object_schema = b.object_schema 
            AND r.object_name = b.object_name
        WHERE r.lock_status = 'PENDING' 
          AND b.lock_status = 'GRANTED'
          AND b.owner_thread_id != r.owner_thread_id
        LIMIT 5
    """))
    
    locks = result.fetchall()
    if locks:
        for row in locks:
            print(f"  表: {row[0]}.{row[1]}")
            print(f"    等待: PID={row[3]}, 锁={row[6]}")
            print(f"    阻塞: PID={row[5]}, 锁={row[8]}")
    else:
        print("  无表锁等待")
    
    # 4. 检查最近慢查询
    print("\n【4】慢查询统计（最近）:")
    result = conn.execute(text("""
        SELECT 
            DIGEST_TEXT as query,
            COUNT_STAR as exec_count,
            AVG_TIMER_WAIT/1000000000 as avg_time_ms,
            MAX_TIMER_WAIT/1000000000 as max_time_ms
        FROM performance_schema.events_statements_summary_by_digest
        WHERE DIGEST_TEXT LIKE '%INSERT%'
           OR DIGEST_TEXT LIKE '%LOAD%'
        ORDER BY AVG_TIMER_WAIT DESC
        LIMIT 5
    """))
    
    for row in result:
        print(f"  执行{row[1]}次, 平均{row[2]:.2f}ms, 最大{row[3]:.2f}ms")
        print(f"    {row[0][:80]}...")
    
    # 5. 检查表状态（碎片、行数）
    print("\n【5】相关表状态:")
    result = conn.execute(text("""
        SELECT 
            table_name,
            table_rows,
            data_length/1024/1024 as data_mb,
            index_length/1024/1024 as index_mb,
            data_free/1024/1024 as free_mb
        FROM information_schema.tables
        WHERE table_schema = 'gs'
          AND table_name LIKE 'data_gpsj_day_%'
        ORDER BY data_length DESC
        LIMIT 10
    """))
    
    for row in result:
        print(f"  {row[0]}: {row[1]}行, 数据{row[2]:.1f}MB, 索引{row[3]:.1f}MB, 碎片{row[4]:.1f}MB")
    
    # 6. 检查 MySQL 配置
    print("\n【6】关键配置参数:")
    configs = [
        'innodb_buffer_pool_size',
        'innodb_log_file_size',
        'innodb_flush_log_at_trx_commit',
        'max_allowed_packet',
        'bulk_insert_buffer_size'
    ]
    
    for config in configs:
        result = conn.execute(text(f"SHOW VARIABLES LIKE '{config}'"))
        row = result.fetchone()
        if row:
            print(f"  {row[0]} = {row[1]}")
    
    # 7. 检查磁盘 IO
    print("\n【7】InnoDB IO 状态:")
    result = conn.execute(text("SHOW GLOBAL STATUS LIKE 'Innodb_data_%'"))
    for row in result:
        print(f"  {row[0]} = {row[1]}")
    
    print("\n" + "=" * 70)
