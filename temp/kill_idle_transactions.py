#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全终止空闲长事务"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text
import time

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 安全终止空闲长事务（Sleep状态且超过30分钟）
idle_pids = [28666, 28676, 28667, 28668]

with engine.connect() as conn:
    print('安全终止空闲长事务（不影响业务插入）')
    print('=' * 60)
    
    killed = 0
    for pid in idle_pids:
        try:
            # 确认是Sleep状态
            result = conn.execute(text(f'SELECT COMMAND, TIME FROM INFORMATION_SCHEMA.PROCESSLIST WHERE ID = {pid}'))
            row = result.fetchone()
            
            if row and row[0] == 'Sleep' and row[1] > 1800:
                conn.execute(text(f'KILL {pid}'))
                print(f'[OK] 终止空闲连接 PID={pid}, 空闲{row[1]}秒')
                killed += 1
            else:
                status = row[0] if row else 'None'
                print(f'[SKIP] PID={pid} 状态={status}, 跳过')
        except Exception as e:
            print(f'[INFO] PID={pid}: {e}')
    
    print('=' * 60)
    print(f'终止完成: {killed}/{len(idle_pids)}')
    
    # 等待Purge清理
    time.sleep(3)
    
    # 检查结果
    result = conn.execute(text('SELECT COUNT(*) FROM information_schema.innodb_trx'))
    remaining = result.fetchone()[0]
    print(f'剩余活跃事务: {remaining}')
    
    result = conn.execute(text('SHOW ENGINE INNODB STATUS'))
    status = result.fetchone()[2]
    for line in status.split('\n'):
        if 'History list length' in line:
            print(f'当前 {line.strip()}')
            break
    
    # 检查是否有活跃的插入
    result = conn.execute(text("""
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.PROCESSLIST 
        WHERE COMMAND = 'Query' 
          AND INFO LIKE '%INSERT%'
    """))
    insert_count = result.fetchone()[0]
    print(f'当前活跃插入: {insert_count}')
