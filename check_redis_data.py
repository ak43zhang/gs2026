#!/usr/bin/env python3
"""
检查Redis中2026-04-28的数据
"""
import redis

r = redis.Redis(host='localhost', port=6379, db=0)

print("=" * 80)
print("Redis数据检查")
print("=" * 80)

# 查找2026-04-28相关的key
keys = r.keys('*20260428*')
print(f"\n包含20260428的key: {len(keys)}个")

# 显示前10个
for key in keys[:10]:
    key_str = key.decode() if isinstance(key, bytes) else key
    key_type = r.type(key).decode() if isinstance(r.type(key), bytes) else r.type(key)
    print(f"  - {key_str} (类型: {key_type})")

# 检查15:00:00的数据
print("\n\n检查15:00:00的数据...")
key_15 = 'monitor_gp_sssj_20260428:15:00:00'
data = r.get(key_15)
if data:
    print(f"  数据存在，大小: {len(data)} bytes")
else:
    print(f"  数据不存在！")

# 检查是否有时间戳列表
print("\n\n检查时间戳列表...")
ts_key = 'monitor_gp_sssj_20260428:timestamps'
timestamps = r.lrange(ts_key, 0, 5)
if timestamps:
    print(f"  时间戳数量: {r.llen(ts_key)}")
    print(f"  前5个: {[t.decode() if isinstance(t, bytes) else t for t in timestamps]}")
else:
    print(f"  时间戳列表不存在！")

print("\n" + "=" * 80)
