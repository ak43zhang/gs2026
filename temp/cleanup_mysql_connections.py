#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理长时间空闲的 MySQL 连接"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    # 查找空闲超过2小时（7200秒）的连接
    result = conn.execute(text("""
        SELECT 
            ID,
            USER,
            HOST,
            TIME,
            COMMAND
        FROM INFORMATION_SCHEMA.PROCESSLIST
        WHERE USER != 'system user'
          AND COMMAND = 'Sleep'
          AND TIME > 7200
        ORDER BY TIME DESC
    """))
    
    connections = result.fetchall()
    
    print(f"找到 {len(connections)} 个空闲超过2小时的连接\n")
    
    if len(connections) == 0:
        print("没有需要清理的连接")
        sys.exit(0)
    
    print(f"{'ID':<10} {'USER':<15} {'HOST':<25} {'TIME(秒)':<12}")
    print("-" * 65)
    
    for row in connections:
        print(f"{row[0]:<10} {row[1]:<15} {row[2]:<25} {row[3]:<12}")
    
    # 清理这些连接
    print("\n正在清理...")
    killed = 0
    for row in connections:
        try:
            conn.execute(text(f"KILL {row[0]}"))
            print(f"  Killed connection {row[0]} (idle {row[3]}s)")
            killed += 1
        except Exception as e:
            print(f"  Failed to kill {row[0]}: {e}")
    
    print(f"\n清理完成: 终止了 {killed} 个连接")
    
    # 显示清理后的连接数
    result = conn.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
    row = result.fetchone()
    print(f"当前连接数: {row[1]}")
