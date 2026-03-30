#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 InnoDB 未清理事务"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    print("=" * 70)
    print("InnoDB 未清理事务分析")
    print("=" * 70)
    
    # 1. 查看活跃事务
    print("\n【1】活跃事务列表:")
    result = conn.execute(text("""
        SELECT 
            trx_id,
            trx_mysql_thread_id,
            trx_state,
            TIMESTAMPDIFF(SECOND, trx_started, NOW()) as trx_seconds,
            LEFT(trx_tables_locked, 20) as tables_locked,
            LEFT(trx_tables_in_use, 20) as tables_in_use
        FROM information_schema.innodb_trx
        ORDER BY trx_started
        LIMIT 20
    """))
    
    count = 0
    for row in result:
        count += 1
        print(f"  TRX={row[0]}, PID={row[1]}, 状态={row[2]}, 运行{row[3]}秒")
    
    if count == 0:
        print("  无活跃事务")
    elif count >= 20:
        print(f"  ... 还有更多事务")
    
    # 2. 查看锁等待
    print("\n【2】锁等待情况:")
    result = conn.execute(text("""
        SELECT 
            r.trx_id as waiting_trx,
            r.trx_mysql_thread_id as waiting_pid,
            b.trx_id as blocking_trx,
            b.trx_mysql_thread_id as blocking_pid,
            w.lock_mode as waiting_lock,
            w.lock_type as waiting_type,
            b.lock_mode as blocking_lock
        FROM information_schema.innodb_lock_waits w
        JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_trx_id
        JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_trx_id
        LIMIT 10
    """))
    
    locks = list(result)
    if locks:
        for row in locks:
            print(f"  等待: TRX={row[0]}, PID={row[1]}")
            print(f"  阻塞: TRX={row[2]}, PID={row[3]}")
    else:
        print("  无锁等待")
    
    # 3. 查看历史事务（已提交但未清理）
    print("\n【3】History List Length 详情:")
    result = conn.execute(text("SHOW ENGINE INNODB STATUS"))
    status = result.fetchone()[2]
    
    in_trx_section = False
    for line in status.split('\n'):
        if '---TRANSACTION' in line:
            in_trx_section = True
        if in_trx_section:
            if 'History list length' in line:
                print(f"  {line.strip()}")
            elif '---TRANSACTION' in line and 'ACTIVE' in line:
                print(f"  {line.strip()}")
            elif len(line.strip()) > 0 and not line.startswith('--------'):
                if 'MySQL thread id' in line or 'query id' in line:
                    print(f"    {line.strip()}")
    
    # 4. 查看长时间运行的连接
    print("\n【4】长时间运行的连接 (Sleep状态但事务未提交):")
    result = conn.execute(text("""
        SELECT 
            ID,
            USER,
            HOST,
            DB,
            COMMAND,
            TIME,
            STATE
        FROM INFORMATION_SCHEMA.PROCESSLIST
        WHERE COMMAND = 'Sleep'
          AND TIME > 3600
          AND USER != 'system user'
        ORDER BY TIME DESC
        LIMIT 10
    """))
    
    for row in result:
        print(f"  PID={row[0]}, 空闲{row[5]}秒, 用户={row[1]}, 数据库={row[3]}")
    
    # 5. 查看未提交事务的连接
    print("\n【5】有未提交事务的连接:")
    result = conn.execute(text("""
        SELECT 
            p.ID,
            p.USER,
            p.HOST,
            p.DB,
            p.TIME,
            p.STATE,
            t.trx_state,
            TIMESTAMPDIFF(SECOND, t.trx_started, NOW()) as trx_age
        FROM information_schema.innodb_trx t
        JOIN information_schema.PROCESSLIST p ON t.trx_mysql_thread_id = p.ID
        ORDER BY t.trx_started
        LIMIT 10
    """))
    
    for row in result:
        print(f"  PID={row[0]}, 事务状态={row[6]}, 事务年龄={row[7]}秒, 连接空闲={row[4]}秒")
    
    print("\n" + "=" * 70)
