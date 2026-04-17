#!/usr/bin/env python3
"""执行数据库变更 - 添加 deep_analysis 字段"""

import sys
sys.path.insert(0, 'src')

from sqlalchemy import create_engine, text

# 数据库连接
url = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4'
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 执行 ALTER TABLE
sql = """ALTER TABLE analysis_news_detail_2026 
ADD COLUMN deep_analysis TEXT NULL COMMENT '深度分析（JSON数组）' 
AFTER sector_details;"""

try:
    with engine.connect() as conn:
        print("执行 SQL:")
        print(sql)
        print()
        
        conn.execute(text(sql))
        conn.commit()
        print("✅ 数据库字段添加成功")
        
        # 验证
        result = conn.execute(text("SHOW COLUMNS FROM analysis_news_detail_2026 LIKE 'deep_analysis'"))
        row = result.fetchone()
        if row:
            print(f"\n字段信息:")
            print(f"  名称: {row[0]}")
            print(f"  类型: {row[1]}")
            print(f"  可空: {row[2]}")
            print(f"  注释: {row[8]}")
        else:
            print("⚠️ 未找到字段，请检查")
            
except Exception as e:
    print(f"❌ 执行失败: {e}")
    sys.exit(1)
