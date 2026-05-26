"""
检查300763数据并测试API
"""
from sqlalchemy import create_engine, text
import json

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 1. 检查300763数据
    print("=== 1. 检查300763数据 ===")
    result = conn.execute(text("SELECT id, date, time, stock_code, stock_name, level FROM buy_point_candidates WHERE stock_code = '300763'"))
    rows = result.fetchall()
    if rows:
        for row in rows:
            print(f"  ID={row[0]}, Date={row[1]}, Time={row[2]}, Code={row[3]}, Name={row[4]}, Level={row[5]}")
    else:
        print("  未找到300763的数据")
    
    # 2. 检查所有数据
    print("\n=== 2. 所有数据 ===")
    result = conn.execute(text("SELECT date, COUNT(*) FROM buy_point_candidates GROUP BY date"))
    for row in result:
        print(f"  Date={row[0]}, Count={row[1]}")
    
    # 3. 测试查询条件
    print("\n=== 3. 测试查询条件 (2026-05-19) ===")
    result = conn.execute(text("SELECT COUNT(*) FROM buy_point_candidates WHERE date BETWEEN '2026-05-19' AND '2026-05-19'"))
    count = result.fetchone()[0]
    print(f"  2026-05-19记录数: {count}")
    
    # 4. 检查日期格式
    print("\n=== 4. 检查日期字段类型 ===")
    result = conn.execute(text("SELECT date, time FROM buy_point_candidates LIMIT 3"))
    for row in result:
        print(f"  date={row[0]} (type={type(row[0])}), time={row[1]} (type={type(row[1])})")
