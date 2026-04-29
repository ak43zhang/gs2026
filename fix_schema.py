from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 检查字段是否存在
    result = conn.execute(text("DESCRIBE monitor_gp_sssj_20260424"))
    columns = [row[0] for row in result.fetchall()]
    print(f"Current columns: {columns}")
    
    # 添加缺失字段
    if 'main_net_amount' not in columns:
        conn.execute(text("ALTER TABLE monitor_gp_sssj_20260424 ADD COLUMN main_net_amount DECIMAL(15,2) DEFAULT 0"))
        print("Added: main_net_amount")
    
    if 'cumulative_main_net' not in columns:
        conn.execute(text("ALTER TABLE monitor_gp_sssj_20260424 ADD COLUMN cumulative_main_net DECIMAL(15,2) DEFAULT 0"))
        print("Added: cumulative_main_net")
    
    if 'main_behavior' not in columns:
        conn.execute(text("ALTER TABLE monitor_gp_sssj_20260424 ADD COLUMN main_behavior VARCHAR(20) DEFAULT NULL"))
        print("Added: main_behavior")
    
    if 'main_confidence' not in columns:
        conn.execute(text("ALTER TABLE monitor_gp_sssj_20260424 ADD COLUMN main_confidence DECIMAL(3,2) DEFAULT 0"))
        print("Added: main_confidence")
    
    conn.commit()
    print("\nAll fields added successfully!")
    
    # 验证
    result = conn.execute(text("DESCRIBE monitor_gp_sssj_20260424"))
    new_columns = [row[0] for row in result.fetchall()]
    print(f"\nNew columns: {new_columns}")
