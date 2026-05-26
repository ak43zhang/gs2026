"""Analyze MySQL storage usage"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 1. Total database size
    r = conn.execute(text("""
        SELECT table_schema, 
               ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) AS size_gb,
               COUNT(*) as table_count
        FROM information_schema.TABLES 
        WHERE table_schema = 'gs'
        GROUP BY table_schema
    """))
    row = r.fetchone()
    print(f"=== Database 'gs' ===")
    print(f"  Total: {row[1]} GB, {row[2]} tables")

    # 2. Top 30 tables by size
    print(f"\n=== Top 30 tables by size ===")
    r = conn.execute(text("""
        SELECT table_name,
               ROUND((data_length + index_length) / 1024 / 1024, 1) AS size_mb,
               table_rows
        FROM information_schema.TABLES
        WHERE table_schema = 'gs'
        ORDER BY (data_length + index_length) DESC
        LIMIT 30
    """))
    for row in r.fetchall():
        print(f"  {row[0]:50s}  {row[1]:>8.1f} MB  rows={row[2]}")

    # 3. Table name pattern analysis (monitor_gp_sssj_*, monitor_zq_sssj_*, etc.)
    print(f"\n=== Table groups by prefix ===")
    r = conn.execute(text("""
        SELECT 
            CASE 
                WHEN table_name REGEXP '^monitor_gp_sssj_[0-9]' THEN 'monitor_gp_sssj_*'
                WHEN table_name REGEXP '^monitor_zq_sssj_[0-9]' THEN 'monitor_zq_sssj_*'
                WHEN table_name REGEXP '^monitor_hy_sssj_[0-9]' THEN 'monitor_hy_sssj_*'
                WHEN table_name REGEXP '^monitor_gp_top30_[0-9]' THEN 'monitor_gp_top30_*'
                WHEN table_name REGEXP '^monitor_zq_top30_[0-9]' THEN 'monitor_zq_top30_*'
                WHEN table_name REGEXP '^monitor_hy_top30_[0-9]' THEN 'monitor_hy_top30_*'
                WHEN table_name REGEXP '^monitor_gp_apqd_[0-9]' THEN 'monitor_gp_apqd_*'
                WHEN table_name REGEXP '^monitor_dp_signal_[0-9]' THEN 'monitor_dp_signal_*'
                ELSE table_name
            END AS tbl_group,
            COUNT(*) AS cnt,
            ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) AS total_gb,
            MIN(table_name) AS earliest,
            MAX(table_name) AS latest
        FROM information_schema.TABLES
        WHERE table_schema = 'gs'
        GROUP BY tbl_group
        ORDER BY total_gb DESC
    """))
    for row in r.fetchall():
        print(f"  {row[0]:30s}  cnt={row[1]:>3d}  size={row[2]:>6.2f} GB  range=[{row[3]} ~ {row[4]}]")

    # 4. Disk usage
    print(f"\n=== MySQL data directory size ===")
    r = conn.execute(text("SELECT @@datadir"))
    print(f"  datadir: {r.fetchone()[0]}")
