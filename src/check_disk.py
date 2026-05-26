#!/usr/bin/env python
"""检查 MySQL 磁盘空间"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    # 检查数据目录磁盘空间
    result = conn.execute(text("SHOW VARIABLES LIKE 'datadir'"))
    datadir = result.fetchone()
    print(f"MySQL 数据目录: {datadir[1] if datadir else 'unknown'}")
    
    # 检查数据库大小
    result = conn.execute(text("""
        SELECT 
            table_schema,
            ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) AS size_gb
        FROM information_schema.tables 
        WHERE table_schema = 'gs'
        GROUP BY table_schema
    """))
    row = result.fetchone()
    if row:
        print(f"数据库 gs 大小: {row[1]} GB")
    else:
        print("无法获取数据库大小")
    
    # 检查最大的表
    print("\n最大的10个表:")
    result = conn.execute(text("""
        SELECT 
            table_name,
            ROUND((data_length + index_length) / 1024 / 1024, 2) AS size_mb
        FROM information_schema.tables 
        WHERE table_schema = 'gs'
        ORDER BY (data_length + index_length) DESC
        LIMIT 10
    """))
    for row in result.fetchall():
        print(f"  {row[0]}: {row[1]} MB")
    
    # 测试创建表
    print("\n测试创建新表...")
    try:
        conn.execute(text("CREATE TABLE test_disk_space (id INT PRIMARY KEY)"))
        conn.execute(text("DROP TABLE test_disk_space"))
        conn.commit()
        print("[OK] 可以创建新表，磁盘空间已释放")
    except Exception as e:
        print(f"[FAIL] 无法创建表: {e}")
