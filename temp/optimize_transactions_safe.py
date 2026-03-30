#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事务和慢查询优化（不影响业务插入）"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text
import time

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

print("=" * 70)
print("事务和慢查询优化（安全模式 - 不影响插入）")
print("=" * 70)

with engine.connect() as conn:
    # 1. 查看当前长事务（不终止，只分析）
    print("\n【1】当前长事务分析")
    print("-" * 70)
    result = conn.execute(text("""
        SELECT 
            t.trx_id,
            t.trx_mysql_thread_id as pid,
            t.trx_state,
            TIMESTAMPDIFF(SECOND, t.trx_started, NOW()) as trx_seconds,
            p.COMMAND,
            p.TIME as conn_time,
            LEFT(p.INFO, 50) as sql_text
        FROM information_schema.innodb_trx t
        LEFT JOIN information_schema.PROCESSLIST p ON t.trx_mysql_thread_id = p.ID
        ORDER BY t.trx_started
    """))
    
    long_transactions = []
    for row in result:
        status = ""
        if row[3] > 3600:
            status = "[超过1小时]"
        elif row[3] > 600:
            status = "[超过10分钟]"
        
        print(f"TRX={row[0]}, PID={row[1]}, 状态={row[2]}, 运行{row[3]}秒 {status}")
        print(f"  连接状态={row[4]}, 连接空闲={row[5]}秒")
        if row[6]:
            print(f"  SQL: {row[6]}...")
        
        if row[3] > 3600 and row[4] == 'Sleep':
            long_transactions.append((row[0], row[1], row[3]))
    
    print(f"\n发现 {len(long_transactions)} 个超过1小时的空闲事务")
    
    # 2. 安全终止空闲长事务（只终止Sleep状态的）
    if long_transactions:
        print("\n【2】安全终止空闲长事务")
        print("-" * 70)
        print("只终止空闲(Sleep)状态的长事务，不影响活跃插入...")
        
        killed = 0
        for trx_id, pid, seconds in long_transactions:
            try:
                # 再次确认是Sleep状态
                result = conn.execute(text(f"SELECT COMMAND FROM information_schema.PROCESSLIST WHERE ID = {pid}"))
                cmd = result.fetchone()
                
                if cmd and cmd[0] == 'Sleep':
                    conn.execute(text(f"KILL {pid}"))
                    print(f"  [OK] 终止空闲事务 PID={pid}, 已空闲{seconds}秒")
                    killed += 1
                else:
                    print(f"  [SKIP] PID={pid} 不是空闲状态，跳过")
            except Exception as e:
                print(f"  [FAIL] 终止 PID={pid} 失败: {e}")
        
        print(f"\n终止完成: {killed}/{len(long_transactions)} 个空闲事务")
    
    # 3. 查看慢查询（只分析，不终止）
    print("\n【3】慢查询分析")
    print("-" * 70)
    result = conn.execute(text("""
        SELECT 
            ID,
            USER,
            HOST,
            DB,
            COMMAND,
            TIME,
            STATE,
            LEFT(INFO, 60) as sql_text
        FROM INFORMATION_SCHEMA.PROCESSLIST
        WHERE COMMAND != 'Sleep'
          AND USER != 'system user'
          AND TIME > 60
        ORDER BY TIME DESC
    """))
    
    slow_queries = []
    for row in result:
        print(f"PID={row[0]}, 运行{row[5]}秒, 状态={row[6]}, 命令={row[4]}")
        if row[7]:
            print(f"  SQL: {row[7]}...")
        
        # 只标记SELECT查询，不标记INSERT
        if row[4] == 'Query' and row[7] and 'SELECT' in row[7].upper():
            slow_queries.append((row[0], row[5], row[7]))
    
    print(f"\n发现 {len(slow_queries)} 个慢SELECT查询")
    
    # 4. 终止慢SELECT查询（不影响INSERT）
    if slow_queries:
        print("\n【4】终止慢SELECT查询（不影响插入）")
        print("-" * 70)
        
        killed = 0
        for pid, seconds, sql in slow_queries:
            if seconds > 300:  # 只终止超过5分钟的
                try:
                    conn.execute(text(f"KILL {pid}"))
                    print(f"  [OK] 终止慢查询 PID={pid}, 运行{seconds}秒")
                    killed += 1
                except Exception as e:
                    print(f"  [FAIL] 终止 PID={pid} 失败: {e}")
        
        print(f"\n终止完成: {killed}/{len(slow_queries)} 个慢查询")
    
    # 5. 优化Purge（加速历史版本清理）
    print("\n【5】优化Purge配置")
    print("-" * 70)
    
    # 查看当前Purge配置
    result = conn.execute(text("SHOW VARIABLES LIKE 'innodb_purge%'"))
    print("当前Purge配置:")
    for row in result:
        print(f"  {row[0]} = {row[1]}")
    
    # 增加Purge线程数（如果当前较少）
    try:
        result = conn.execute(text("SELECT @@innodb_purge_threads"))
        current = result.fetchone()[0]
        if current < 4:
            conn.execute(text("SET GLOBAL innodb_purge_threads = 4"))
            print(f"  [OK] 增加Purge线程数: {current} -> 4")
        else:
            print(f"  [OK] Purge线程数已足够: {current}")
    except Exception as e:
        print(f"  [INFO] 无法动态修改Purge线程: {e}")
    
    # 6. 查看优化效果
    print("\n【6】优化效果检查")
    print("-" * 70)
    
    time.sleep(2)  # 等待Purge工作
    
    result = conn.execute(text("SELECT COUNT(*) FROM information_schema.innodb_trx"))
    remaining_trx = result.fetchone()[0]
    print(f"剩余活跃事务: {remaining_trx}")
    
    result = conn.execute(text("SHOW ENGINE INNODB STATUS"))
    status = result.fetchone()[2]
    for line in status.split('\n'):
        if 'History list length' in line:
            print(f"当前 {line.strip()}")
            break
    
    result = conn.execute(text("SHOW STATUS LIKE 'Threads_running'"))
    running = result.fetchone()[1]
    print(f"正在运行的线程: {running}")

print("\n" + "=" * 70)
print("优化完成（未影响业务插入）")
print("=" * 70)
