#!/usr/bin/env python3
"""排查 c3470a316119a20794d548a503c513dc 数据问题"""
import sys
sys.path.insert(0, 'src')

from sqlalchemy import create_engine, text

url = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4'
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

TEST_HASH = 'c3470a316119a20794d548a503c513dc'

with engine.connect() as conn:
    for table in ['news_cls2026', 'news_combine2026']:
        result = conn.execute(text(f"SELECT `内容hash`, analysis FROM {table} WHERE `内容hash`='{TEST_HASH}'"))
        row = result.fetchone()
        if row:
            print(f"表: {table}")
            print(f"  hash: {row[0]}")
            print(f"  analysis: {row[1]}")
            print()
