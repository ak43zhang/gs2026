"""
检查表结构和唯一键
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    result = conn.execute(text("SHOW CREATE TABLE buy_point_candidates"))
    row = result.fetchone()
    print(row[1])
