"""Check and add chaoduan_score column"""
import traceback
try:
    from sqlalchemy import create_engine, text
    url = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4'
    e = create_engine(url, connect_args={'connect_timeout': 10})
    with e.connect() as conn:
        r = conn.execute(text(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='gs' AND TABLE_NAME='analysis_domain_detail_2026' "
            "AND COLUMN_NAME='chaoduan_score'"
        ))
        if r.fetchone():
            print("Column 'chaoduan_score' already exists")
        else:
            conn.execute(text(
                "ALTER TABLE analysis_domain_detail_2026 "
                "ADD COLUMN chaoduan_score INT DEFAULT 0 AFTER business_impact_score"
            ))
            conn.commit()
            print("Column 'chaoduan_score' added successfully")
except Exception as ex:
    traceback.print_exc()
    print(f"FAILED: {ex}")
