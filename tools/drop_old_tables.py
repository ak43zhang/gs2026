"""
删除旧的历史数据表释放存储空间
"""
from sqlalchemy import create_engine, text
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from gs2026.dashboard2.config import Config

# 要删除的表
tables_to_drop = [
    'monitor_gp_sssj_20260309',
    'monitor_gp_sssj_20260310',
    'monitor_gp_sssj_20260311'
]

def drop_tables():
    engine = create_engine(Config.MYSQL_URI, pool_recycle=3600, pool_pre_ping=True)
    
    with engine.connect() as conn:
        for table in tables_to_drop:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                print(f"✅ 已删除表: {table}")
            except Exception as e:
                print(f"❌ 删除失败 {table}: {e}")
        
        conn.commit()
    
    print("\n完成！")

if __name__ == '__main__':
    drop_tables()
