"""
添加 retry_count 字段到 stock_anomaly 表
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 检查字段是否存在
    result = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = 'gs' 
        AND TABLE_NAME = 'stock_anomaly' 
        AND COLUMN_NAME = 'retry_count'
    """))
    exists = result.fetchone()[0] > 0
    
    if not exists:
        print("添加 retry_count 字段...")
        conn.execute(text("""
            ALTER TABLE stock_anomaly 
            ADD COLUMN retry_count INT DEFAULT 0 COMMENT '重试次数'
        """))
        conn.commit()
        print("✓ 字段添加成功")
    else:
        print("✓ retry_count 字段已存在")
