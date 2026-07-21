"""
修复：清除盛德转债和三江转债在monitor_zq_sssj_20260720中的脏数据(误写入的0717数据)
然后从Redis bond:tick缓存(今天实时采集的正确数据)回写到MySQL
"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import config_util, redis_util
from sqlalchemy import text

# 初始化
redis_util.init_redis(
    host=config_util.get_config('common.redis.host'),
    port=config_util.get_config('common.redis.port'),
    decode_responses=False
)
r = redis_util._get_redis_client()
engine = config_util.get_engine()

BONDS = {'118058': '盛德转债', '123273': '三江转债'}
TODAY = '20260720'
TABLE = f'monitor_zq_sssj_{TODAY}'

print("=" * 50)
print("1. 删除MySQL中这两只债券的脏数据")
print("=" * 50)

with engine.connect() as conn:
    for code, name in BONDS.items():
        r_count = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE} WHERE bond_code = :code"), {'code': code}).scalar()
        print(f"  {name}({code}) 当前MySQL行数: {r_count}")
        conn.execute(text(f"DELETE FROM {TABLE} WHERE bond_code = :code"), {'code': code})
        print(f"  已删除")
    conn.commit()
    print("  COMMITTED")

print()
print("=" * 50)
print("2. 从Redis读取今天的正确数据")
print("=" * 50)

import json

for code, name in BONDS.items():
    key = f"bond:tick:{code}:{TODAY}"
    data = r.hgetall(key)
    count = len(data)
    print(f"  {name}({code}): Redis中有 {count} 条今日数据")
    
    if count == 0:
        print(f"    ⚠️ Redis也无数据，跳过")
        continue
    
    # 解析Redis数据
    ticks = []
    for time_key, json_val in data.items():
        t = time_key.decode() if isinstance(time_key, bytes) else time_key
        v = json.loads(json_val.decode() if isinstance(json_val, bytes) else json_val)
        v['time'] = t
        v['bond_code'] = code
        ticks.append(v)
    
    ticks.sort(key=lambda x: x['time'])
    print(f"    时间范围: {ticks[0]['time']} ~ {ticks[-1]['time']}")
    
    # 写入MySQL
    print(f"    写入MySQL...")
    with engine.connect() as conn:
        batch_size = 500
        inserted = 0
        for i in range(0, len(ticks), batch_size):
            batch = ticks[i:i+batch_size]
            values = []
            for tick in batch:
                values.append({
                    'bond_code': code,
                    'bond_name': name,
                    'time': tick['time'],
                    'price': tick.get('price', 0),
                    'change_pct': tick.get('change_pct', 0),
                    'amount': tick.get('amount', 0),
                    'volume': tick.get('volume', 0),
                    'high': tick.get('high', 0),
                    'low': tick.get('low', 0),
                    'open': tick.get('open', 0),
                    'pre_close': tick.get('pre_close', 0),
                })
            
            sql = text(f"""
                INSERT INTO {TABLE} (bond_code, bond_name, time, price, change_pct, amount, volume, high, low, `open`, pre_close)
                VALUES (:bond_code, :bond_name, :time, :price, :change_pct, :amount, :volume, :high, :low, :open, :pre_close)
            """)
            conn.execute(sql, values)
            inserted += len(batch)
        
        conn.commit()
        print(f"    ✅ 已写入 {inserted} 条")

print()
print("=" * 50)
print("3. 验证")
print("=" * 50)

with engine.connect() as conn:
    for code, name in BONDS.items():
        row = conn.execute(text(
            f"SELECT COUNT(*) cnt, MIN(time) t1, MAX(time) t2 FROM {TABLE} WHERE bond_code = :code"
        ), {'code': code}).fetchone()
        print(f"  {name}({code}): {row[0]}条, {row[1]} ~ {row[2]}")

print()
print("DONE. 现在刷新页面应该显示今天的正确数据了。")
