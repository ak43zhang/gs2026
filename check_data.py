from sqlalchemy import create_engine, text
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
with engine.connect() as conn:
    # 检查 000539 的数据
    query = text("SELECT stock_code, change_pct, main_net_amount, time FROM monitor_gp_sssj_20260428 WHERE stock_code = '000539' ORDER BY time DESC LIMIT 3")
    results = conn.execute(query).fetchall()
    print('000539 latest data:')
    for r in results:
        print(f'  time={r[3]}, change_pct={r[1]}, main_net_amount={r[2]}')
