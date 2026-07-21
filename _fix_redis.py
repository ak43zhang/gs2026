"""清理三江转债和盛德转债的旧Redis缓存，确认今天数据存在"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import config_util, redis_util

# 初始化Redis
redis_util.init_redis(
    host=config_util.get_config('common.redis.host'),
    port=config_util.get_config('common.redis.port'),
    decode_responses=False
)
r = redis_util._get_redis_client()

BONDS = {'118058': '盛德转债', '123273': '三江转债'}
TODAY = '20260720'

print("=" * 50)
print("1. 清理旧缓存")
print("=" * 50)

for code, name in BONDS.items():
    # 扫描所有非今天的 bond:tick:{code}:* 键
    pattern = f"bond:tick:{code}:*"
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = r.scan(cursor, match=pattern, count=100)
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            if TODAY not in key_str:
                r.delete(key)
                deleted += 1
                print(f"  DEL {key_str}")
        if cursor == 0:
            break
    print(f"  {name}({code}): 删除 {deleted} 个旧key")

print()
print("=" * 50)
print("2. 检查今天的数据")
print("=" * 50)

needs_backfill = []
for code, name in BONDS.items():
    key = f"bond:tick:{code}:{TODAY}"
    count = r.hlen(key)
    print(f"  {name}({code}): bond:tick:{code}:{TODAY} = {count} 条")
    if count == 0:
        needs_backfill.append(code)

print()
print("=" * 50)
print("3. 回填缺失数据")
print("=" * 50)

if needs_backfill:
    from sqlalchemy import text
    from gs2026.redis.bond_tick_cache import BondTickCache
    import json
    
    engine = config_util.get_engine()
    cache = BondTickCache.get_instance()
    
    for code in needs_backfill:
        name = BONDS[code]
        print(f"  回填 {name}({code})...")
        with engine.connect() as conn:
            sql = text(
                "SELECT time, price, change_pct, amount, volume, high, low, `open`, pre_close "
                "FROM monitor_zq_sssj_20260720 "
                "WHERE bond_code = :code ORDER BY time"
            )
            rows = conn.execute(sql, {'code': code}).fetchall()
        
        if rows:
            ticks = []
            for row in rows:
                ticks.append({
                    'time': str(row[0]),
                    'price': float(row[1]) if row[1] else 0,
                    'change_pct': float(row[2]) if row[2] else 0,
                    'amount': float(row[3]) if row[3] else 0,
                    'volume': float(row[4]) if row[4] else 0,
                    'high': float(row[5]) if row[5] else 0,
                    'low': float(row[6]) if row[6] else 0,
                    'open': float(row[7]) if row[7] else 0,
                    'pre_close': float(row[8]) if row[8] else 0,
                })
            cache.write_batch(code, ticks, TODAY)
            print(f"    已回填 {len(ticks)} 条")
        else:
            print(f"    MySQL中无今天数据")
else:
    print("  无需回填，两只债券今天的Redis数据已存在")

print()
print("=" * 50)
print("4. 最终验证")
print("=" * 50)

for code, name in BONDS.items():
    key = f"bond:tick:{code}:{TODAY}"
    count = r.hlen(key)
    ttl = r.ttl(key)
    print(f"  {name}({code}): {count} 条, TTL={ttl}秒")

print()
print("DONE. 请重启dashboard服务使代码改动生效。")
