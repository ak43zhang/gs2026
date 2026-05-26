import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
from gs2026.dashboard.config import Config

uri = f"mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8mb4"
engine = create_engine(uri)
with engine.connect() as conn:
    # Check bond table columns
    result = conn.execute(text("SHOW COLUMNS FROM monitor_zq_sssj_20260518 LIKE '%price%'"))
    cols = [row[0] for row in result]
    print(f'Bond table price columns: {cols}')
    
    # Also check stock table
    result2 = conn.execute(text("SHOW COLUMNS FROM monitor_gp_sssj_20260518 LIKE '%price%'"))
    cols2 = [row[0] for row in result2]
    print(f'Stock table price columns: {cols2}')
    
    # Sample data
    result3 = conn.execute(text("SELECT bond_code, change_pct, price FROM monitor_zq_sssj_20260518 ORDER BY time DESC LIMIT 3"))
    for row in result3:
        print(f'Sample: {row}')
