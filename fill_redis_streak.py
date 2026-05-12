#!/usr/bin/env python3
"""将每只股票的最后一次连续上攻值填充到Redis最新tick中"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.utils import config_util, redis_util

url = config_util.get_config('common.url')
engine = create_engine(url)

redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)

date_str = '20260512'
sssj_table = f"monitor_gp_sssj_{date_str}"

print("=" * 60)
print("填充Redis - 每只股票最后一次连续上攻值")
print("=" * 60)

# 1. 从MySQL查每只股票的最大consecutive_attacks值
print("\n1. 查询每只股票的最大连续上攻值...")
sql = f"""
    SELECT stock_code, MAX(consecutive_attacks) as max_streak
    FROM {sssj_table}
    WHERE consecutive_attacks > 0
    GROUP BY stock_code
    ORDER BY max_streak DESC
"""
df_max = pd.read_sql(sql, engine)
df_max['stock_code'] = df_max['stock_code'].astype(str).str.zfill(6)
streak_map = dict(zip(df_max['stock_code'], df_max['max_streak'].astype(int)))
print(f"   有记录的股票: {len(streak_map)}")
print(f"   Top5: {list(streak_map.items())[:5]}")

# 2. 获取Redis中最新tick时间
client = redis_util._get_redis_client()
ts_key = f"{sssj_table}:timestamps"
latest_ts = client.lindex(ts_key, 0)
if latest_ts:
    latest_tick = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
else:
    latest_tick = '14:56:45'
print(f"\n2. 最新tick: {latest_tick}")

# 3. 更新最新tick的Redis sssj数据
print(f"\n3. 更新Redis ({latest_tick})...")
redis_key = f"{sssj_table}:{latest_tick}"
df_sssj = redis_util.load_dataframe_by_key(redis_key, use_compression=False)

if df_sssj is not None and not df_sssj.empty:
    code_col = 'stock_code' if 'stock_code' in df_sssj.columns else 'code'
    df_sssj[code_col] = df_sssj[code_col].astype(str).str.zfill(6)
    
    # 用最大连续上攻值填充（保留当前tick的真实值，只补充历史最大值）
    if 'consecutive_attacks' not in df_sssj.columns:
        df_sssj['consecutive_attacks'] = 0
    
    # 对于当前值为0的股票，填充历史最大值
    df_sssj['consecutive_attacks'] = df_sssj.apply(
        lambda row: int(row['consecutive_attacks']) if int(row.get('consecutive_attacks', 0)) > 0 
                     else streak_map.get(str(row[code_col]).zfill(6), 0), 
        axis=1
    ).astype(int)
    
    non_zero = (df_sssj['consecutive_attacks'] > 0).sum()
    print(f"   sssj记录: {len(df_sssj)}")
    print(f"   有连续上攻的: {non_zero}")
    
    # 保存回Redis
    redis_util.save_dataframe_to_redis(df_sssj, sssj_table, latest_tick, 64800, use_compression=False)
    print(f"   [OK] Redis已更新")
    
    # 验证
    df_v = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
    v_count = (pd.to_numeric(df_v['consecutive_attacks'], errors='coerce').fillna(0) > 0).sum()
    print(f"   [OK] 验证: {v_count}只股票有值")
    
    # 显示排行中可能的股票
    df_v[code_col] = df_v[code_col].astype(str).str.zfill(6)
    top_stocks = df_v.nlargest(15, 'consecutive_attacks')
    print(f"\n   Top15:")
    for _, r in top_stocks.iterrows():
        print(f"     {r[code_col]}: {r['consecutive_attacks']}")

print("\n[OK] 完成！刷新前端页面查看。")
