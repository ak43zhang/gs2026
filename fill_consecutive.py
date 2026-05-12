#!/usr/bin/env python3
"""填充今日连续上攻次数到sssj表的Redis缓存 - 修复版"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from sqlalchemy import create_engine
from gs2026.utils import config_util, redis_util

url = config_util.get_config('common.url')
engine = create_engine(url)

redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)

date_str = '20260512'
top30_table = f"monitor_gp_top30_{date_str}"
sssj_table = f"monitor_gp_sssj_{date_str}"

print("=" * 60)
print(f"填充连续上攻次数 - {date_str}")
print("=" * 60)

# 1. 获取所有tick时间（正序）
print("\n1. 获取所有tick时间...")
ticks_df = pd.read_sql(f"SELECT DISTINCT time FROM {top30_table} ORDER BY time", engine)
ticks = ticks_df['time'].tolist()
print(f"   总tick数: {len(ticks)}")

# 2. 获取每个tick的top30股票集合（统一6位code）
print("\n2. 获取每个tick的top30股票...")
all_top30 = pd.read_sql(f"SELECT DISTINCT code, time FROM {top30_table}", engine)
all_top30['code'] = all_top30['code'].astype(str).str.zfill(6)

tick_codes = {}
for t in ticks:
    tick_codes[t] = set(all_top30[all_top30['time'] == t]['code'].values)

# 调试：看最后几个tick的股票数量
last3 = ticks[-3:]
for t in last3:
    print(f"   tick {t}: {len(tick_codes[t])} 只股票, 样本: {list(tick_codes[t])[:3]}")

# 3. 正向遍历，计算连续上攻次数
print("\n3. 计算连续上攻次数...")
streak = {}
all_codes = set()
for t in ticks:
    codes_in_tick = tick_codes.get(t, set())
    all_codes.update(codes_in_tick)
    
    new_streak = {}
    for code in all_codes:
        if code in codes_in_tick:
            new_streak[code] = streak.get(code, 0) + 1
        else:
            new_streak[code] = 0
    streak = new_streak

non_zero = sum(1 for v in streak.values() if v > 0)
max_streak = max(streak.values()) if streak else 0
print(f"   有连续上攻记录的股票: {non_zero}")
print(f"   最大连续次数: {max_streak}")

top10 = sorted(streak.items(), key=lambda x: x[1], reverse=True)[:10]
print(f"\n   Top10:")
for code, cnt in top10:
    print(f"     {code}: {cnt}")

# 4. 更新Redis
latest_tick = ticks[-1]
print(f"\n4. 更新Redis ({latest_tick})...")

redis_key = f"{sssj_table}:{latest_tick}"
df_sssj = redis_util.load_dataframe_by_key(redis_key, use_compression=False)

if df_sssj is not None and not df_sssj.empty:
    code_col = 'stock_code' if 'stock_code' in df_sssj.columns else 'code'
    df_sssj[code_col] = df_sssj[code_col].astype(str).str.zfill(6)
    
    # 调试：检查格式
    sample_sssj = df_sssj[code_col].head(3).tolist()
    sample_streak = list(streak.keys())[:3]
    print(f"   sssj code样本: {sample_sssj}")
    print(f"   streak code样本: {sample_streak}")
    
    # 填充
    df_sssj['consecutive_attacks'] = df_sssj[code_col].map(streak).fillna(0).astype(int)
    
    non_zero_sssj = (df_sssj['consecutive_attacks'] > 0).sum()
    print(f"   sssj记录数: {len(df_sssj)}")
    print(f"   有连续上攻的: {non_zero_sssj}")
    
    # 保存回Redis
    redis_util.save_dataframe_to_redis(df_sssj, sssj_table, latest_tick, 64800, use_compression=False)
    print(f"   [OK] 已更新Redis")
    
    # 验证
    df_v = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
    if 'consecutive_attacks' in df_v.columns:
        v_non_zero = (pd.to_numeric(df_v['consecutive_attacks'], errors='coerce').fillna(0) > 0).sum()
        print(f"   [OK] 验证: {v_non_zero}只有记录")
        # 显示有值的
        df_v[code_col] = df_v[code_col].astype(str).str.zfill(6)
        hits = df_v[pd.to_numeric(df_v['consecutive_attacks'], errors='coerce').fillna(0) > 0]
        if not hits.empty:
            print(f"   有值的股票:")
            for _, r in hits.head(10).iterrows():
                print(f"     {r[code_col]}: {r['consecutive_attacks']}")

print("\n[OK] 完成！刷新前端页面查看。")
