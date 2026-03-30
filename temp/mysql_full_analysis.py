#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MySQL 入库性能全面分析"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text
import time

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

print("=" * 80)
print("MySQL 入库性能全面分析报告")
print("=" * 80)

with engine.connect() as conn:
    # 1. 当前事务状态
    print("\n【1】当前事务状态")
    print("-" * 80)
    result = conn.execute(text("SELECT COUNT(*) as cnt FROM information_schema.innodb_trx"))
    trx_count = result.fetchone()[0]
    print(f"活跃事务数: {trx_count}")
    
    result = conn.execute(text("SHOW ENGINE INNODB STATUS"))
    status = result.fetchone()[2]
    for line in status.split('\n'):
        if 'History list length' in line:
            print(f"未清理版本: {line.strip()}")
        if 'Log sequence number' in line:
            print(f"日志序列: {line.strip()}")
            break
    
    # 2. 表锁和行锁
    print("\n【2】锁状态")
    print("-" * 80)
    result = conn.execute(text("""
        SHOW GLOBAL STATUS 
        WHERE Variable_name IN (
            'Innodb_row_lock_waits', 'Innodb_row_lock_current_waits',
            'Table_locks_waited', 'Innodb_deadlocks'
        )
    """))
    for row in result:
        print(f"{row[0]}: {row[1]}")
    
    # 3. 连接状态
    print("\n【3】连接状态")
    print("-" * 80)
    result = conn.execute(text("SHOW STATUS LIKE 'Threads_%'"))
    for row in result:
        print(f"{row[0]}: {row[1]}")
    
    # 4. 表状态（重点关注插入慢的表）
    print("\n【4】目标表状态")
    print("-" * 80)
    result = conn.execute(text("""
        SELECT 
            table_name,
            table_rows,
            ROUND(data_length/1024/1024, 1) as data_mb,
            ROUND(index_length/1024/1024, 1) as index_mb,
            ROUND(data_free/1024/1024, 1) as free_mb,
            ROUND((data_free / NULLIF(data_length, 0)) * 100, 1) as frag_pct
        FROM information_schema.tables
        WHERE table_schema = 'gs'
          AND table_name LIKE 'data_gpsj_day%'
        ORDER BY data_length DESC
        LIMIT 10
    """))
    
    print(f"{'表名':<35} {'行数':<12} {'数据MB':<10} {'索引MB':<10} {'碎片MB':<10} {'碎片%':<8}")
    print("-" * 80)
    for row in result:
        frag = f"{row[5]}%" if row[5] else "0%"
        print(f"{row[0]:<35} {row[1]:<12} {row[2]:<10} {row[3]:<10} {row[4]:<10} {frag:<8}")
    
    # 5. 关键配置
    print("\n【5】关键配置参数")
    print("-" * 80)
    params = [
        'innodb_buffer_pool_size',
        'innodb_log_file_size',
        'innodb_flush_log_at_trx_commit',
        'innodb_flush_method',
        'max_allowed_packet',
        'innodb_io_capacity',
        'innodb_read_io_threads',
        'innodb_write_io_threads',
        'innodb_purge_threads'
    ]
    
    for param in params:
        try:
            result = conn.execute(text(f"SHOW VARIABLES LIKE '{param}'"))
            row = result.fetchone()
            if row:
                print(f"{row[0]}: {row[1]}")
        except:
            pass
    
    # 6. IO状态
    print("\n【6】IO状态")
    print("-" * 80)
    result = conn.execute(text("""
        SHOW GLOBAL STATUS 
        WHERE Variable_name LIKE 'Innodb_data%' 
           OR Variable_name LIKE 'Innodb_log%'
           OR Variable_name LIKE 'Innodb_pages%'
    """))
    for row in result:
        print(f"{row[0]}: {row[1]}")
    
    # 7. 插入性能测试
    print("\n【7】插入性能测试")
    print("-" * 80)
    
    # 创建测试表
    try:
        conn.execute(text("DROP TABLE IF EXISTS _perf_test"))
        conn.execute(text("""
            CREATE TABLE _perf_test (
                id INT AUTO_INCREMENT PRIMARY KEY,
                stock_code VARCHAR(10),
                trade_date DATE,
                open_price DECIMAL(10,2),
                close_price DECIMAL(10,2),
                volume BIGINT,
                amount DECIMAL(15,2)
            ) ENGINE=InnoDB
        """))
        
        # 单条插入测试
        start = time.time()
        for i in range(100):
            conn.execute(text(f"""
                INSERT INTO _perf_test (stock_code, trade_date, open_price, close_price, volume, amount)
                VALUES ('TEST{i}', '2026-03-30', 100.00, 101.00, 1000000, 100000000.00)
            """))
            conn.commit()
        single_time = time.time() - start
        
        # 批量插入测试
        conn.execute(text("TRUNCATE TABLE _perf_test"))
        start = time.time()
        values = []
        for i in range(100):
            values.append(f"('TEST{i}', '2026-03-30', 100.00, 101.00, 1000000, 100000000.00)")
        
        conn.execute(text(f"""
            INSERT INTO _perf_test (stock_code, trade_date, open_price, close_price, volume, amount)
            VALUES {','.join(values)}
        """))
        conn.commit()
        batch_time = time.time() - start
        
        print(f"单条插入100条: {single_time:.3f}秒 ({100/single_time:.1f} 条/秒)")
        print(f"批量插入100条: {batch_time:.3f}秒 ({100/batch_time:.1f} 条/秒)")
        print(f"批量提升: {single_time/batch_time:.1f}倍")
        
        # 清理
        conn.execute(text("DROP TABLE IF EXISTS _perf_test"))
        
    except Exception as e:
        print(f"测试失败: {e}")
    
    # 8. 慢查询
    print("\n【8】最近的慢查询")
    print("-" * 80)
    try:
        result = conn.execute(text("""
            SELECT 
                DIGEST_TEXT as query,
                COUNT_STAR as exec_count,
                ROUND(AVG_TIMER_WAIT/1000000000, 2) as avg_time_ms,
                ROUND(MAX_TIMER_WAIT/1000000000, 2) as max_time_ms
            FROM performance_schema.events_statements_summary_by_digest
            WHERE DIGEST_TEXT LIKE '%INSERT%'
            ORDER BY AVG_TIMER_WAIT DESC
            LIMIT 5
        """))
        
        for row in result:
            print(f"执行{row[1]}次, 平均{row[2]}ms, 最大{row[3]}ms")
            print(f"  SQL: {row[0][:60]}...")
    except Exception as e:
        print(f"无法获取慢查询: {e}")

print("\n" + "=" * 80)
