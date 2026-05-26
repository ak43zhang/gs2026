"""
检查今日买点候选数据是否入库
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 1. 检查今天数据
    result = conn.execute(text("SELECT COUNT(*) FROM buy_point_candidates WHERE date = '2026-05-19'"))
    count = result.fetchone()[0]
    print(f"2026-05-19 total records: {count}")
    
    if count > 0:
        result = conn.execute(text("SELECT id, date, time, stock_code, stock_name, level FROM buy_point_candidates WHERE date = '2026-05-19' ORDER BY time"))
        for row in result:
            print(f"  ID={row[0]} {row[1]} {row[2]} {row[3]} {row[4]} Level={row[5]}")
    
    # 2. 检查所有日期
    print("\nAll dates:")
    result = conn.execute(text("SELECT date, COUNT(*) as cnt FROM buy_point_candidates GROUP BY date ORDER BY date DESC"))
    for row in result:
        print(f"  {row[0]}: {row[1]} records")
