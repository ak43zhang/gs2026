"""
添加record_id字段和唯一键
"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 添加record_id字段
    try:
        conn.execute(text("ALTER TABLE buy_point_candidates ADD COLUMN record_id VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'MD5(stock_code+date+time)' AFTER id"))
        print("Added record_id column")
    except Exception as e:
        print(f"Column may exist: {e}")
    
    # 添加唯一键
    try:
        conn.execute(text("ALTER TABLE buy_point_candidates ADD UNIQUE KEY uk_record_id (record_id)"))
        print("Added unique key")
    except Exception as e:
        print(f"Key may exist: {e}")
    
    # 为已有数据补充record_id
    conn.execute(text("UPDATE buy_point_candidates SET record_id = MD5(CONCAT(stock_code, date, time)) WHERE record_id = ''"))
    conn.commit()
    print("Updated existing records")
    
    # 验证
    result = conn.execute(text("SELECT id, record_id, stock_code FROM buy_point_candidates LIMIT 3"))
    for row in result:
        print(f"  ID={row[0]}, record_id={row[1][:16]}..., code={row[2]}")
