from sqlalchemy import create_engine, text
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
with engine.connect() as conn:
    # 检查 15:00:00 的数据
    result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260428 WHERE time = '15:00:00'")).fetchone()
    print(f'MySQL rows at 15:00:00: {result[0]}')
    
    # 检查有哪些时间点
    result = conn.execute(text("SELECT DISTINCT time FROM monitor_gp_sssj_20260428 ORDER BY time DESC LIMIT 5")).fetchall()
    print(f'Latest times in MySQL:')
    for r in result:
        print(f'  {r[0]}')
