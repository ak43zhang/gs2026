from sqlalchemy import create_engine, text
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
with engine.connect() as conn:
    # 检查 000539 和 002217 在 15:00:00 的数据
    query = text("""
        SELECT stock_code, change_pct, main_net_amount 
        FROM monitor_gp_sssj_20260428 
        WHERE time = '15:00:00' AND stock_code IN ('000539', '002217')
    """)
    results = conn.execute(query).fetchall()
    print('Query results:')
    for r in results:
        print(f'  code={r[0]}, change_pct={r[1]}, main_net_amount={r[2]}')
