#!/usr/bin/env python3
"""检查 deep_analysis 字段数据情况"""

import sys
sys.path.insert(0, 'src')

from sqlalchemy import create_engine, text
import json

# 数据库连接
url = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4'
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 检查表结构
print("=== 检查表结构 ===")
with engine.connect() as conn:
    result = conn.execute(text("SHOW COLUMNS FROM analysis_news_detail_2026 LIKE 'deep_analysis'"))
    row = result.fetchone()
    if row:
        print(f"字段存在: {row[0]} | 类型: {row[1]} | 可空: {row[2]}")
    else:
        print("❌ deep_analysis 字段不存在")

# 检查数据
print("\n=== 检查数据 ===")
with engine.connect() as conn:
    # 统计总数
    result = conn.execute(text("SELECT COUNT(*) as cnt FROM analysis_news_detail_2026"))
    total = result.fetchone()[0]
    print(f"总记录数: {total}")
    
    # 统计有 deep_analysis 的记录
    result = conn.execute(text("SELECT COUNT(*) as cnt FROM analysis_news_detail_2026 WHERE deep_analysis IS NOT NULL AND deep_analysis != '' AND deep_analysis != '[]'"))
    with_data = result.fetchone()[0]
    print(f"有 deep_analysis 的记录: {with_data}")
    
    # 查看几条样本数据
    print("\n=== 样本数据 ===")
    result = conn.execute(text("""
        SELECT content_hash, title, deep_analysis 
        FROM analysis_news_detail_2026 
        WHERE deep_analysis IS NOT NULL AND deep_analysis != '' AND deep_analysis != '[]'
        LIMIT 3
    """))
    for row in result:
        print(f"\n标题: {row[1][:50]}...")
        print(f"deep_analysis: {row[2][:200] if row[2] else 'NULL'}...")
