"""快速检查今天的top30表"""
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 检查表是否存在
    result = conn.execute(text("SHOW TABLES LIKE 'monitor_gp_top30_20260513'"))
    exists = result.fetchone() is not None
    print(f"表 monitor_gp_top30_20260513 存在: {exists}")
    
    if exists:
        # 检查条数
        result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_top30_20260513"))
        count = result.scalar()
        print(f"总条数: {count}")
