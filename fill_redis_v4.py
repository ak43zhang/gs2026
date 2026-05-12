import sys, io
sys.stdout = io.TextIOWrapper(open(r'F:\pyworkspace2026\gs2026\fill_log.txt', 'wb'), encoding='utf-8')
sys.stderr = sys.stdout

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
import pandas as pd
from sqlalchemy import create_engine
from gs2026.utils import config_util, redis_util

try:
    url = config_util.get_config('common.url')
    engine = create_engine(url)
    redis_util.init_redis(host='localhost', port=6379, decode_responses=False)
    print("Init OK")
    sys.stdout.flush()

    date_str = '20260512'
    sssj_table = f'monitor_gp_sssj_{date_str}'

    print("Testing SQL...")
    sys.stdout.flush()
    
    sql = f"SELECT stock_code, MAX(consecutive_attacks) as ms FROM {sssj_table} WHERE consecutive_attacks > 0 GROUP BY stock_code ORDER BY ms DESC"
    df_max = pd.read_sql(sql, engine)
    df_max['stock_code'] = df_max['stock_code'].astype(str).str.zfill(6)
    streak_map = dict(zip(df_max['stock_code'], df_max['ms'].astype(int)))
    print(f"Streak map: {len(streak_map)} stocks")
    sys.stdout.flush()

    client = redis_util._get_redis_client()
    ts = client.lindex(f'{sssj_table}:timestamps', 0)
    tick = ts.decode() if ts else '14:56:45'
    print(f"Latest tick: {tick}")
    sys.stdout.flush()

    rk = f'{sssj_table}:{tick}'
    df_r = redis_util.load_dataframe_by_key(rk, use_compression=False)
    print(f"Redis loaded: {len(df_r) if df_r is not None else 'None'} rows")
    sys.stdout.flush()

    if df_r is not None and not df_r.empty:
        code_col = 'stock_code' if 'stock_code' in df_r.columns else 'code'
        df_r[code_col] = df_r[code_col].astype(str).str.zfill(6)
        df_r['consecutive_attacks'] = df_r[code_col].map(streak_map).fillna(0).astype(int)
        non_zero = (df_r['consecutive_attacks'] > 0).sum()
        print(f"Non-zero: {non_zero}")
        sys.stdout.flush()

        redis_util.save_dataframe_to_redis(df_r, sssj_table, tick, 64800, use_compression=False)
        print("Saved to Redis")
        sys.stdout.flush()

        df_v = redis_util.load_dataframe_by_key(rk, use_compression=False)
        vn = (pd.to_numeric(df_v['consecutive_attacks'], errors='coerce').fillna(0) > 0).sum()
        print(f"Verified: {vn}")

        df_v[code_col] = df_v[code_col].astype(str).str.zfill(6)
        top = df_v.nlargest(10, 'consecutive_attacks')[[code_col, 'consecutive_attacks']]
        for _, r in top.iterrows():
            print(f"  {r[code_col]}: {r['consecutive_attacks']}")

    print("DONE")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

sys.stdout.flush()
