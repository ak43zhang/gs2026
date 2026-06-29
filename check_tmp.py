from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 大盘表字段
    r = conn.execute(text("SHOW COLUMNS FROM monitor_gp_apqd_20260629"))
    print("大盘表字段:")
    for row in r.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    # 行业表字段
    r2 = conn.execute(text("SHOW COLUMNS FROM monitor_bk_apqd_20260629"))
    print("\n行业表字段:")
    for row in r2.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    # 测试查询
    print("\n测试大盘查询:")
    r3 = conn.execute(text("SELECT time, avg_change_pct as change_pct FROM monitor_gp_apqd_20260629 LIMIT 3"))
    for row in r3.fetchall():
        print(f"  {row}")
    
    print("\n测试行业查询:")
    r4 = conn.execute(text("SELECT time, avg_change_pct as change_pct FROM monitor_bk_apqd_20260629 WHERE bk_name='半导体' LIMIT 3"))
    for row in r4.fetchall():
        print(f"  {row}")
