from sqlalchemy import create_engine, text
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
with engine.connect() as conn:
    result = conn.execute(text("SHOW TABLES LIKE 'monitor_gp_sssj_20260424'"))
    tables = result.fetchall()
    print(f"Tables: {tables}")
    
    if tables:
        result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260424"))
        count = result.scalar()
        print(f"Record count: {count}")
