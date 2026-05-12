#!/usr/bin/env python3
"""在sssj表中添加consecutive_attacks字段并回填数据"""

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
top30_table = f"monitor_gp_top30_{date_str}"
sssj_table = f"monitor_gp_sssj_{date_str}"

print("=" * 60)
print(f"添加并填充 consecutive_attacks 字段 - {date_str}")
print("=" * 60)

# 1. ALTER TABLE 添加字段
print("\n1. 添加字段到sssj表...")
with engine.connect() as conn:
    try:
        conn.execute(text(f"ALTER TABLE {sssj_table} ADD COLUMN consecutive_attacks INT DEFAULT 0"))
        conn.commit()
        print("   [OK] 字段已添加")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("   [OK] 字段已存在")
        else:
            print(f"   [FAIL] {e}")

# 2. 获取所有tick时间（正序）
print("\n2. 获取tick数据...")
ticks_df = pd.read_sql(f"SELECT DISTINCT time FROM {top30_table} ORDER BY time", engine)
ticks = ticks_df['time'].tolist()
print(f"   总tick数: {len(ticks)}")

# 3. 获取每个tick的top30股票
all_top30 = pd.read_sql(f"SELECT DISTINCT code, time FROM {top30_table}", engine)
all_top30['code'] = all_top30['code'].astype(str).str.zfill(6)
tick_codes = {}
for t in ticks:
    tick_codes[t] = set(all_top30[all_top30['time'] == t]['code'].values)

# 4. 正向遍历，计算每个tick每只股票的连续上攻次数
print("\n3. 计算所有tick的连续上攻次数...")
streak = {}
all_codes = set()
tick_streaks = {}  # {tick: {code: streak_value}}

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
    
    # 只记录非零值（减少更新量）
    tick_streaks[t] = {code: val for code, val in streak.items() if val > 0}

total_updates = sum(len(v) for v in tick_streaks.values())
print(f"   需要更新的记录数: {total_updates}")

# 5. 批量UPDATE到MySQL
print("\n4. 更新MySQL...")
batch_size = 500
updated = 0

with engine.connect() as conn:
    for t in ticks:
        streak_data = tick_streaks.get(t, {})
        if not streak_data:
            continue
        
        # 批量更新：用CASE WHEN
        codes = list(streak_data.keys())
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            case_parts = []
            for code in batch:
                val = streak_data[code]
                case_parts.append(f"WHEN '{code}' THEN {val}")
            
            codes_str = ','.join([f"'{c}'" for c in batch])
            case_sql = ' '.join(case_parts)
            
            sql = f"""
                UPDATE {sssj_table} 
                SET consecutive_attacks = CASE stock_code {case_sql} END
                WHERE time = '{t}' AND stock_code IN ({codes_str})
            """
            conn.execute(text(sql))
            updated += len(batch)
    
    conn.commit()

print(f"   [OK] 更新完成: {updated} 批次")

# 6. 更新Redis（最新tick + 最近几个tick）
print("\n5. 更新Redis缓存...")
# 更新最近10个tick的Redis缓存
recent_ticks = ticks[-10:]
for t in recent_ticks:
    redis_key = f"{sssj_table}:{t}"
    df_sssj = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
    if df_sssj is not None and not df_sssj.empty:
        code_col = 'stock_code' if 'stock_code' in df_sssj.columns else 'code'
        df_sssj[code_col] = df_sssj[code_col].astype(str).str.zfill(6)
        
        streak_data = tick_streaks.get(t, {})
        df_sssj['consecutive_attacks'] = df_sssj[code_col].map(streak_data).fillna(0).astype(int)
        
        redis_util.save_dataframe_to_redis(df_sssj, sssj_table, t, 64800, use_compression=False)

print(f"   [OK] 已更新 {len(recent_ticks)} 个tick的Redis缓存")

# 7. 验证
print("\n6. 验证...")
verify_sql = f"""
    SELECT time, stock_code, consecutive_attacks 
    FROM {sssj_table} 
    WHERE consecutive_attacks > 0 
    ORDER BY consecutive_attacks DESC 
    LIMIT 20
"""
df_verify = pd.read_sql(verify_sql, engine)
print(f"   有连续上攻记录的样本:")
for _, row in df_verify.iterrows():
    print(f"     {row['time']} | {row['stock_code']} | 连续{row['consecutive_attacks']}次")

# 统计
stats_sql = f"""
    SELECT COUNT(DISTINCT stock_code) as stock_count, 
           MAX(consecutive_attacks) as max_streak,
           COUNT(*) as total_records
    FROM {sssj_table} 
    WHERE consecutive_attacks > 0
"""
df_stats = pd.read_sql(stats_sql, engine)
print(f"\n   统计:")
print(f"   有连续上攻记录的股票数: {df_stats.iloc[0]['stock_count']}")
print(f"   最大连续次数: {df_stats.iloc[0]['max_streak']}")
print(f"   非零记录总数: {df_stats.iloc[0]['total_records']}")

print("\n" + "=" * 60)
print("[OK] 填充完成！刷新前端页面查看。")
print("=" * 60)
