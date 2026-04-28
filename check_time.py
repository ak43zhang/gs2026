from gs2026.utils import redis_util

# 检查 15:00:00 的 key
key = 'monitor_gp_sssj_20260428:15:00:00'
df = redis_util.load_dataframe_by_key(key, use_compression=False)
if df is not None:
    print(f'Found data at 15:00:00 in Redis, rows: {len(df)}')
    print(df[['stock_code', 'change_pct']].head(3))
else:
    print('No data at 15:00:00 in Redis')

# 检查 MySQL
from sqlalchemy import create_engine, text
engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_sssj_20260428 WHERE time = '15:00:00'")).fetchone()
    print(f'MySQL rows at 15:00:00: {result[0]}')
    
    # 检查有哪些时间点
    result = conn.execute(text("SELECT DISTINCT time FROM monitor_gp_sssj_20260428 ORDER BY time DESC LIMIT 5")).fetchall()
    print(f'Latest times in MySQL:')
    for r in result:
        print(f'  {r[0]}')
