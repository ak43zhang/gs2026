"""
测试 Redis 连接池多线程写入
"""
import sys
sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from gs2026.utils import config_util, redis_util
from sqlalchemy import create_engine

# 初始化 Redis（使用连接池）
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False, max_connections=20)

# 数据库连接
url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

# 测试表
table_name = 'monitor_gp_sssj_20260324'
test_time = datetime.now().strftime('%H:%M:%S')

print(f"[TEST] 测试表: {table_name}")
print(f"[TEST] 测试时间: {test_time}")

# 1. 从 MySQL 读取数据
print("[TEST] 从 MySQL 读取数据...")
sql = f"SELECT * FROM {table_name} WHERE time = '10:45:12' LIMIT 100"
df = pd.read_sql(sql, engine)
print(f"[TEST] 读取到 {len(df)} 条数据")

if df.empty:
    print("[ERROR] MySQL 中没有数据!")
    sys.exit(1)

# 2. 并发写入测试
print("[TEST] 并发写入 Redis（10线程，每人10条）...")

def write_to_redis(thread_id, df_subset, time_str):
    """单个线程写入"""
    try:
        redis_util.save_dataframe_to_redis(
            df_subset, table_name, f"{time_str}_{thread_id}", 3600, use_compression=False
        )
        return f"线程 {thread_id}: 成功写入 {len(df_subset)} 条"
    except Exception as e:
        return f"线程 {thread_id}: 失败 - {e}"

# 分割数据为10份
df_chunks = [df.iloc[i:i+10].copy() for i in range(0, min(100, len(df)), 10)]

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {}
    for i, chunk in enumerate(df_chunks[:10]):
        future = executor.submit(write_to_redis, i, chunk, test_time)
        futures[future] = i
    
    results = []
    for future in as_completed(futures):
        result = future.result()
        results.append(result)
        print(f"  {result}")

# 3. 验证读取
print("[TEST] 验证读取...")
import redis
client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)

success_count = 0
for i in range(10):
    key = f"{table_name}:{test_time}_{i}"
    exists = client.exists(key)
    if exists:
        success_count += 1
        # 验证数据完整性
        data = client.get(key)
        if data:
            df_check = pd.read_json(data.decode('utf-8'), orient='records')
            print(f"  Key {key}: 存在，{len(df_check)} 条数据")
        else:
            print(f"  Key {key}: 存在但无数据")
    else:
        print(f"  Key {key}: 不存在")

print(f"\n[TEST] 结果: {success_count}/10 个 key 写入成功")

if success_count == 10:
    print("[SUCCESS] 连接池多线程测试通过!")
else:
    print("[FAILED] 部分数据写入失败")

# 4. 检查连接池状态
print("\n[TEST] 连接池信息:")
if redis_util._redis_pool:
    print(f"  连接池最大连接数: {redis_util._redis_pool.max_connections}")
