import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
import pandas as pd
from sqlalchemy import create_engine
from gs2026.utils import config_util, redis_util

try:
    url = config_util.get_config('common.url')
    engine = create_engine(url)
    redis_util.init_redis(host='localhost', port=6379, decode_responses=False)

    date_str = '20260512'
    sssj_table = f'monitor_gp_sssj_{date_str}'

    # 1. 查最大连续上攻值
    sql = f"SELECT stock_code, MAX(consecutive_attacks) as ms FROM {sssj_table} WHERE consecutive_attacks > 0 GROUP BY stock_code ORDER BY ms DESC"
    df_max = pd.read_sql(sql, engine)
    df_max['stock_code'] = df_max['stock_code'].astype(str).str.zfill(6)
    streak_map = dict(zip(df_max['stock_code'], df_max['ms'].astype(int)))
    print(f"有记录股票: {len(streak_map)}")
    print(f"Top5: {list(streak_map.items())[:5]}")

    # 2. 获取最新tick
    client = redis_util._get_redis_client()
    ts = client.lindex(f'{sssj_table}:timestamps', 0)
    tick = ts.decode() if ts else '14:56:45'
    print(f"Latest tick: {tick}")

    # 3. 加载Redis
    rk = f'{sssj_table}:{tick}'
    df_r = redis_util.load_dataframe_by_key(rk, use_compression=False)
    if df_r is None or df_r.empty:
        print("Redis data is None/empty!")
        sys.exit(1)
    
    code_col = 'stock_code' if 'stock_code' in df_r.columns else 'code'
    df_r[code_col] = df_r[code_col].astype(str).str.zfill(6)
    print(f"Redis records: {len(df_r)}")
    print(f"Columns: {list(df_r.columns)}")

    # 4. 填充consecutive_attacks
    df_r['consecutive_attacks'] = df_r[code_col].map(streak_map).fillna(0).astype(int)
    non_zero = (df_r['consecutive_attacks'] > 0).sum()
    print(f"Non-zero after fill: {non_zero}")

    # 5. 保存回Redis
    redis_util.save_dataframe_to_redis(df_r, sssj_table, tick, 64800, use_compression=False)
    print("[OK] Saved to Redis")

    # 6. 验证
    df_v = redis_util.load_dataframe_by_key(rk, use_compression=False)
    vn = (pd.to_numeric(df_v['consecutive_attacks'], errors='coerce').fillna(0) > 0).sum()
    print(f"[OK] Verified: {vn} stocks with streak")

    # Top 10
    df_v[code_col] = df_v[code_col].astype(str).str.zfill(6)
    top = df_v.nlargest(10, 'consecutive_attacks')[[code_col, 'consecutive_attacks']]
    print("Top10:")
    for _, r in top.iterrows():
        print(f"  {r[code_col]}: {r['consecutive_attacks']}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
