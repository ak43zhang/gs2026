#!/usr/bin/env python3
"""执行SQL脚本"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard.services.data_service import DataService
from sqlalchemy import text

ds = DataService()
engine = ds.engine

# 检查字段是否存在
check_sql = """
SELECT COUNT(*) FROM information_schema.columns 
WHERE table_schema = DATABASE() 
  AND table_name = 'quant_screen_hits' 
  AND column_name = 'hit_seq_today'
"""

with engine.connect() as conn:
    result = conn.execute(text(check_sql)).scalar()
    if result == 0:
        # 添加字段
        alter_sql = "ALTER TABLE quant_screen_hits ADD COLUMN hit_seq_today INT DEFAULT 1 COMMENT '当天命中序号';"
        conn.execute(text(alter_sql))
        conn.commit()
        print("✓ 添加 hit_seq_today 字段成功")
    else:
        print("✓ hit_seq_today 字段已存在")
    
    # 创建索引
    index_sql = """
    SELECT COUNT(*) FROM information_schema.statistics 
    WHERE table_schema = DATABASE() 
      AND table_name = 'quant_screen_hits' 
      AND index_name = 'idx_bond_date_time'
    """
    result = conn.execute(text(index_sql)).scalar()
    if result == 0:
        conn.execute(text("CREATE INDEX idx_bond_date_time ON quant_screen_hits(bond_code, trade_date, tick_time);"))
        conn.commit()
        print("✓ 创建索引 idx_bond_date_time 成功")
    else:
        print("✓ 索引 idx_bond_date_time 已存在")

print("✓ 数据库变更完成")
