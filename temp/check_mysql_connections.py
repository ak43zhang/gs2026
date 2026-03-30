#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 MySQL 连接数"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    # 查看当前连接数
    result = conn.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
    row = result.fetchone()
    print(f"当前连接数: {row[1]}")
    
    # 查看最大连接数
    result = conn.execute(text("SHOW VARIABLES LIKE 'max_connections'"))
    row = result.fetchone()
    print(f"最大连接数: {row[1]}")
    
    # 查看活跃连接详情
    result = conn.execute(text("""
        SELECT 
            ID,
            USER,
            HOST,
            DB,
            COMMAND,
            TIME,
            STATE,
            LEFT(INFO, 50) as INFO
        FROM INFORMATION_SCHEMA.PROCESSLIST
        WHERE USER != 'system user'
        ORDER BY TIME DESC
    """))
    
    print("\n活跃连接详情:")
    print(f"{'ID':<10} {'USER':<15} {'HOST':<20} {'DB':<10} {'COMMAND':<10} {'TIME':<8} {'STATE':<20}")
    print("-" * 100)
    
    for row in result:
        print(f"{row[0]:<10} {row[1]:<15} {row[2]:<20} {str(row[3]):<10} {row[4]:<10} {row[5]:<8} {str(row[6]):<20}")
