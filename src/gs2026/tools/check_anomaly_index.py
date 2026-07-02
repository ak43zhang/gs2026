"""检查MySQL版本和stock_anomaly索引"""
from sqlalchemy import text
from gs2026.utils import config_util

engine = config_util.get_engine()
with engine.connect() as conn:
    # MySQL版本
    ver = conn.execute(text("SELECT VERSION()")).fetchone()
    print(f"MySQL版本: {ver[0]}")
    
    # 现有索引
    result = conn.execute(text("SHOW INDEX FROM stock_anomaly"))
    rows = result.fetchall()
    print(f"\n现有索引({len(rows)}条):")
    seen = set()
    for r in rows:
        key_name = r[2]
        col_name = r[4]
        if key_name not in seen:
            seen.add(key_name)
            print(f"  {key_name}: {col_name}")
        else:
            print(f"    + {col_name}")
