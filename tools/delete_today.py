"""
删除2026-05-19的所有数据
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    result = conn.execute(text("DELETE FROM buy_point_candidates WHERE date = '2026-05-19'"))
    conn.commit()
    print(f"Deleted: {result.rowcount} rows")
    
    # 验证
    result = conn.execute(text("SELECT COUNT(*) FROM buy_point_candidates WHERE date = '2026-05-19'"))
    count = result.fetchone()[0]
    print(f"Remaining: {count} rows")
