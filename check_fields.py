from sqlalchemy import create_engine, text
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
with engine.connect() as conn:
    # 检查字段
    result = conn.execute(text("DESCRIBE monitor_gp_sssj_20260424"))
    cols = result.fetchall()
    print("Fields:")
    for col in cols:
        print(f"  {col[0]}: {col[1]}")
    
    # 检查change_pct
    print("\nchange_pct check:")
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN change_pct IS NULL THEN 1 ELSE 0 END) as null_cnt,
            SUM(CASE WHEN change_pct = 0 THEN 1 ELSE 0 END) as zero_cnt
        FROM monitor_gp_sssj_20260424
    """))
    row = result.fetchone()
    print(f"  Total: {row[0]}")
    print(f"  NULL: {row[1]}")
    print(f"  Zero: {row[2]}")
    
    # 检查main_net_amount
    print("\nmain_net_amount check:")
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN main_net_amount IS NULL THEN 1 ELSE 0 END) as null_cnt,
            SUM(CASE WHEN main_net_amount = 0 THEN 1 ELSE 0 END) as zero_cnt
        FROM monitor_gp_sssj_20260424
    """))
    row = result.fetchone()
    print(f"  Total: {row[0]}")
    print(f"  NULL: {row[1]}")
    print(f"  Zero: {row[2]}")
    
    # 检查cumulative_main_net
    print("\ncumulative_main_net check:")
    result = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN cumulative_main_net IS NULL THEN 1 ELSE 0 END) as null_cnt,
            SUM(CASE WHEN cumulative_main_net = 0 THEN 1 ELSE 0 END) as zero_cnt
        FROM monitor_gp_sssj_20260424
    """))
    row = result.fetchone()
    print(f"  Total: {row[0]}")
    print(f"  NULL: {row[1]}")
    print(f"  Zero: {row[2]}")
    
    # 对比2026-04-28
    print("\nCompare 2026-04-28:")
    result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260428"))
    count_28 = result.scalar()
    print(f"  2026-04-28: {count_28}")
    result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260424"))
    count_24 = result.fetchone()[0]
    print(f"  2026-04-24: {count_24}")
