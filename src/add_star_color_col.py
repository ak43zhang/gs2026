#!/usr/bin/env python
"""添加 star_color 列到 buy_point_candidates 表"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True, connect_args={'connect_timeout': 10})

with engine.connect() as conn:
    # 检查列是否已存在
    result = conn.execute(text("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'gs' AND TABLE_NAME = 'buy_point_candidates' AND COLUMN_NAME = 'star_color'
    """))
    if result.fetchone():
        print("[SKIP] star_color column already exists")
    else:
        conn.execute(text("ALTER TABLE buy_point_candidates ADD COLUMN star_color VARCHAR(10) DEFAULT 'yellow'"))
        conn.commit()
        print("[OK] Added star_color column to buy_point_candidates")
