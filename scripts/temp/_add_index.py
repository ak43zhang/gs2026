"""给 monitor_zq_sssj 表添加 bond_code 索引，解决全表扫描超时"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import config_util
from sqlalchemy import text

engine = config_util.get_engine()
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE monitor_zq_sssj_20260720 ADD INDEX idx_bond_code (bond_code)"))
        conn.commit()
        print("OK: idx_bond_code added to monitor_zq_sssj_20260720")
    except Exception as e:
        if 'Duplicate' in str(e):
            print("Index already exists")
        else:
            print(f"Error: {e}")
