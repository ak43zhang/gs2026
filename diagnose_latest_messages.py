#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断 latest-messages 性能瓶颈
"""
import time
import requests
from gs2026.utils import redis_util

print('诊断 /api/monitor/latest-messages 性能瓶颈')
print('=' * 60)

# 1. 初始化Redis并检查时间戳数量
redis_util.init_redis()
client = redis_util._get_redis_client()
table_name = "monitor_combine_20260331"
ts_key = f"{table_name}:timestamps"

total_ts = client.llen(ts_key)
print(f'\n1. Redis时间戳统计:')
print(f'   总时间戳数: {total_ts}')

# 2. 获取前18个时间戳
all_ts = client.lrange(ts_key, 0, 17)
print(f'\n2. 前18个时间戳:')
for i, ts in enumerate(all_ts[:5], 1):
    ts_str = ts.decode('utf-8') if isinstance(ts, bytes) else ts
    print(f'   {i}. {ts_str}')
print(f'   ... (共{len(all_ts)}个)')

# 3. 测试单个时间点的数据量
print(f'\n3. 单个时间点数据量:')
for i, ts in enumerate(all_ts[:3], 1):
    ts_str = ts.decode('utf-8') if isinstance(ts, bytes) else ts
    key = f"{table_name}:{ts_str}"
    data = client.get(key)
    if data:
        import pandas as pd
        import io
        df = pd.read_json(io.StringIO(data.decode('utf-8')), orient='records')
        print(f'   {ts_str}: {len(df)} 条记录')

# 4. 测试Pipeline批量获取性能
print(f'\n4. Pipeline批量获取性能:')
start = time.time()
pipe = client.pipeline()
for ts in all_ts:
    ts_str = ts.decode('utf-8') if isinstance(ts, bytes) else ts
    key = f"{table_name}:{ts_str}"
    pipe.get(key)
results = pipe.execute()
pipe_time = (time.time() - start) * 1000
print(f'   Pipeline获取{len(all_ts)}个时间点: {pipe_time:.2f}ms')

# 5. 测试反序列化性能
print(f'\n5. 反序列化性能:')
start = time.time()
total_rows = 0
for data in results:
    if data:
        df = pd.read_json(io.StringIO(data.decode('utf-8')), orient='records')
        total_rows += len(df)
deserialize_time = (time.time() - start) * 1000
print(f'   反序列化{len([r for r in results if r])}个DataFrame: {deserialize_time:.2f}ms')
print(f'   总数据行数: {total_rows}')

# 6. 实际API测试
print(f'\n6. 实际API测试:')
for i in range(2):
    start = time.time()
    resp = requests.get('http://localhost:8080/api/monitor/latest-messages?limit=50', timeout=30)
    elapsed = (time.time() - start) * 1000
    print(f'   请求{i+1}: {elapsed:.2f}ms')

print('\n' + '=' * 60)
print('诊断完成!')
