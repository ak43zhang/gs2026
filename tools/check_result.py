from sqlalchemy import create_engine, text
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*), SUM(level=2), SUM(level=3) FROM buy_point_candidates WHERE date = '2026-05-19'"))
    row = result.fetchone()
    print(f"Total: {row[0]}, 2star={row[1]}, 3star={row[2]}")
    
    # 检查是否有605358的3星数据
    result = conn.execute(text("SELECT time, stock_code, stock_name, level, bond_change_pct FROM buy_point_candidates WHERE date = '2026-05-19' AND stock_code = '605358' ORDER BY time"))
    for r in result:
        print(f"  {r[0]} {r[1]} {r[2]} Lv{r[3]} bond_chg={r[4]}")
