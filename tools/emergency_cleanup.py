"""Emergency: clean binlog + drop legacy tables"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 1. Check binlog size
    print("=== Current binlog ===")
    r = conn.execute(text("SHOW BINARY LOGS"))
    total_mb = 0
    count = 0
    for row in r.fetchall():
        total_mb += row[1] / 1024 / 1024
        count += 1
    print(f"  {count} files, {total_mb:.0f} MB total")

    # 2. Purge binlog (keep 1 day)
    print("\n=== Purging binlog (keep 1 day) ===")
    conn.execute(text("PURGE BINARY LOGS BEFORE DATE(NOW() - INTERVAL 1 DAY)"))
    conn.execute(text("SET GLOBAL binlog_expire_logs_seconds = 86400"))
    conn.commit()

    # Check after purge
    r = conn.execute(text("SHOW BINARY LOGS"))
    after_mb = 0
    after_count = 0
    for row in r.fetchall():
        after_mb += row[1] / 1024 / 1024
        after_count += 1
    print(f"  After: {after_count} files, {after_mb:.0f} MB")
    print(f"  Freed: {total_mb - after_mb:.0f} MB")

    # 3. Drop legacy tables
    print("\n=== Dropping legacy tables ===")
    legacy = [
        'gp_sssj_20260305',
        'gp_sssj_20260306',
        'zq_sssj_20260305',
        'zq_sssj_20260306',
        'zq_apqd_20260305',
        'zq_apqd_20260306',
        'zq_top30_20260306',
        'zq_top_gain_30_20260305',
        'zq_top_speed_30_20260305',
        'monitor_stock_adata_current_20260303',
        'monitor_bond_jsl_20260304',
    ]
    for tbl in legacy:
        try:
            # Check if exists and get size
            r = conn.execute(text(
                f"SELECT ROUND((data_length+index_length)/1024/1024,1) "
                f"FROM information_schema.TABLES "
                f"WHERE table_schema='gs' AND table_name='{tbl}'"
            ))
            row = r.fetchone()
            if row:
                size = row[0]
                conn.execute(text(f"DROP TABLE `{tbl}`"))
                conn.commit()
                print(f"  DROP {tbl} ({size} MB)")
            else:
                print(f"  {tbl} not found, skip")
        except Exception as e:
            print(f"  {tbl} error: {e}")

    # 4. Summary - check disk freed
    print("\n=== Current database size ===")
    r = conn.execute(text(
        "SELECT ROUND(SUM(data_length+index_length)/1024/1024/1024,2) "
        "FROM information_schema.TABLES WHERE table_schema='gs'"
    ))
    print(f"  gs database: {r.fetchone()[0]} GB")
