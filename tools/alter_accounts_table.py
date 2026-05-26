"""执行DDL：accounts表新增is_active字段"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import create_engine, text
from gs2026.utils import config_util

db = config_util.get_config('mysql', 'url')
if isinstance(db, dict):
    url = f"mysql+pymysql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['database']}"
else:
    url = db

engine = create_engine(url)
with engine.connect() as conn:
    try:
        conn.execute(text(
            "ALTER TABLE accounts ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1 "
            "COMMENT '1=valid,0=invalid' AFTER service_type"
        ))
        print("Added is_active column")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("is_active column already exists")
        else:
            raise

    try:
        conn.execute(text("ALTER TABLE accounts ADD INDEX idx_is_active (is_active)"))
        print("Added idx_is_active index")
    except Exception as e:
        if 'Duplicate key name' in str(e):
            print("idx_is_active index already exists")
        else:
            raise

    conn.commit()

    # 验证
    cols = conn.execute(text("SHOW COLUMNS FROM accounts")).fetchall()
    print("\naccounts columns:")
    for c in cols:
        print(f"  {c[0]} ({c[1]}) default={c[4]}")
print("\nDone!")
