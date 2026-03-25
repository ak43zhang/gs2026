"""
测试 data_recovery 的 Redis 写入功能
"""
import sys
sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

import pandas as pd
from gs2026.utils import config_util, redis_util
from sqlalchemy import create_engine

# 初始化 Redis
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)

# 数据库连接
url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 测试表
table_name = 'monitor_gp_sssj_20260324'
time_str = '10:45:12'

print(f"[TEST] 测试表: {table_name}, 时间: {time_str}")

# 1. 从 MySQL 读取数据
print("[TEST] 从 MySQL 读取数据...")
sql = f"SELECT * FROM {table_name} WHERE time = '{time_str}' LIMIT 10"
df = pd.read_sql(sql, engine)
print(f"[TEST] 读取到 {len(df)} 条数据")

if df.empty:
    print("[ERROR] MySQL 中没有数据!")
    sys.exit(1)

# 2. 写入 Redis
print("[TEST] 写入 Redis...")
try:
    redis_util.save_dataframe_to_redis(df, table_name, time_str, 64800, use_compression=False)
    print("[TEST] 写入成功")
except Exception as e:
    print(f"[ERROR] 写入失败: {e}")
    import traceback
    traceback.print_exc()

# 3. 从 Redis 读取验证
print("[TEST] 从 Redis 读取验证...")
key = f"{table_name}:{time_str}"
df_redis = redis_util.load_dataframe_by_key(key, use_compression=False)

if df_redis is not None:
    print(f"[TEST] 从 Redis 读取成功，共 {len(df_redis)} 条数据")
else:
    print("[ERROR] 从 Redis 读取失败!")

# 4. 检查 key 是否存在
print("[TEST] 检查 key 是否存在...")
import redis
client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)
exists = client.exists(key)
print(f"[TEST] Key {key} 存在: {exists}")

# 5. 检查过期时间
if exists:
    ttl = client.ttl(key)
    print(f"[TEST] Key {key} 剩余过期时间: {ttl} 秒")
