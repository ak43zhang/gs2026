#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查找债券相关表"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

with engine.connect() as conn:
    result = conn.execute(text("SHOW TABLES LIKE '%bond%'"))
    print("债券相关表:")
    for row in result:
        print(f"  {row[0]}")
    
    result = conn.execute(text("SHOW TABLES LIKE '%zq%'"))
    print("\nZQ相关表:")
    for row in result:
        print(f"  {row[0]}")
        
    result = conn.execute(text("SHOW TABLES LIKE '%可转债%'"))
    print("\n可转债相关表:")
    for row in result:
        print(f"  {row[0]}")
