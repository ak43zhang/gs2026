"""
直接检查数据库中的价格格式
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 检查monitor_gp_sssj表中的价格
    result = conn.execute(text("SELECT stock_code, price FROM monitor_gp_sssj_20260519 LIMIT 5"))
    print("monitor_gp_sssj_20260519:")
    for row in result:
        code, price = row
        print(f"  {code}: price={price} (type={type(price).__name__})")
