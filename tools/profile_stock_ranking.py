"""Profile stock ranking API - measure each step"""
import sys, time
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache

ds = DataService()
date = '20260518'

print("=== 股票上攻排行 API 性能分析 ===\n")

# Step 1: get_stock_ranking (Redis/MySQL)
t0 = time.time()
data = ds.get_stock_ranking(limit=30, date=date, use_mysql=True)
t1 = time.time()
print(f"1. get_stock_ranking: {(t1-t0)*1000:.0f}ms ({len(data)} items)")

if not data:
    print("No data!")
    sys.exit()

# Step 2: _enrich_stock_data (三层缓存)
t2 = time.time()
cache = get_cache()
codes = [s.get('code', '') for s in data if s.get('code')]
mappings = cache.get_mappings_smart(codes)
for stock in data:
    code = stock.get('code', '')
    m = mappings.get(code)
    if m:
        stock['bond_code'] = m.get('bond_code', '-')
        stock['bond_name'] = m.get('bond_name', '-')
        stock['industry_name'] = m.get('industry_name', '-')
t3 = time.time()
print(f"2. enrich_stock_data: {(t3-t2)*1000:.0f}ms")

# Step 3: _get_latest_sssj_time
from gs2026.utils import redis_util
try:
    redis_util.init_redis()
except:
    pass

t4 = time.time()
# Find latest time
sssj_table = f"monitor_gp_sssj_{date}"
try:
    client = redis_util._get_redis_client()
    ts_key = f"{sssj_table}:timestamps"
    latest_ts = client.lindex(ts_key, 0)
    query_time = latest_ts.decode('utf-8') if latest_ts and isinstance(latest_ts, bytes) else (latest_ts or None)
except:
    query_time = None

if not query_time:
    from sqlalchemy import create_engine, text
    from gs2026.utils import config_util
    url = config_util.get_config('common.url')
    engine = create_engine(url)
    with engine.connect() as conn:
        r = conn.execute(text(f"SELECT MAX(time) FROM {sssj_table}"))
        query_time = str(r.scalar())

t5 = time.time()
print(f"3. get_latest_time: {(t5-t4)*1000:.0f}ms (time={query_time})")

# Step 4: _get_change_pct_and_main_net_batch
import pandas as pd
stock_codes = [s['code'].zfill(6) for s in data if s.get('code')]

t6 = time.time()
# Try Redis first
redis_key = f"{sssj_table}:{query_time}"
df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
t7 = time.time()
print(f"4a. Redis load DataFrame: {(t7-t6)*1000:.0f}ms (got {'%d rows' % len(df) if df is not None else 'None'})")

if df is None or df.empty:
    # MySQL fallback
    t8 = time.time()
    from sqlalchemy import create_engine, text
    from gs2026.utils import config_util
    url = config_util.get_config('common.url')
    engine = create_engine(url)
    codes_str = ','.join([f"'{c}'" for c in stock_codes])
    query = f"SELECT stock_code, change_pct, cumulative_main_net FROM {sssj_table} WHERE time = '{query_time}' AND stock_code IN ({codes_str})"
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    t9 = time.time()
    print(f"4b. MySQL query: {(t9-t8)*1000:.0f}ms ({len(df)} rows)")
else:
    # Extract from Redis DataFrame
    t8 = time.time()
    code_col = 'stock_code' if 'stock_code' in df.columns else 'code'
    df_filtered = df[df[code_col].astype(str).str.zfill(6).isin(stock_codes)]
    t9 = time.time()
    print(f"4b. DataFrame filter: {(t9-t8)*1000:.0f}ms ({len(df_filtered)} of {len(df)} rows)")

total = (t9-t0)*1000
print(f"\n=== 总计: {total:.0f}ms ===")
print(f"\n各步骤占比:")
print(f"  get_stock_ranking: {(t1-t0)*1000:.0f}ms ({(t1-t0)/(t9-t0)*100:.0f}%)")
print(f"  enrich_stock_data: {(t3-t2)*1000:.0f}ms ({(t3-t2)/(t9-t0)*100:.0f}%)")
print(f"  get_latest_time:   {(t5-t4)*1000:.0f}ms ({(t5-t4)/(t9-t0)*100:.0f}%)")
print(f"  load data:         {(t9-t6)*1000:.0f}ms ({(t9-t6)/(t9-t0)*100:.0f}%)")
