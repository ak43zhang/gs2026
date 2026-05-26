#!/usr/bin/env python
"""简化测试 monitor_bond.py 的数据写入"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from datetime import datetime

print("Step 1: 导入模块...")
from gs2026.monitor import monitor_stock as msac
print("  OK")

print("\nStep 2: 初始化 Redis...")
from gs2026.utils import redis_util, config_util
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
print(f"  OK: {redis_host}:{redis_port}")

print("\nStep 3: 创建测试数据...")
date_str = datetime.now().strftime('%Y%m%d')
time_full = datetime.now().strftime('%H:%M:%S')
df = pd.DataFrame({
    'bond_code': ['123001', '123002'],
    'bond_name': ['Test1', 'Test2'],
    'price': [100.5, 101.2],
    'change_pct': [1.5, 2.1],
    'open': [99.0, 100.0],
    'time': [time_full, time_full]
})
print(f"  OK: {len(df)} rows")

print("\nStep 4: 测试 MySQL 写入...")
table_name = f"monitor_zq_sssj_{date_str}"
try:
    msac.save_dataframe(df, table_name, time_full, 3600)
    print("  OK: MySQL write success")
except Exception as e:
    print(f"  FAIL: {e}")

print("\nStep 5: 测试 Redis 写入...")
try:
    redis_util.save_dataframe_to_redis(df, table_name, time_full, 3600, use_compression=False)
    print("  OK: Redis write success")
except Exception as e:
    print(f"  FAIL: {e}")

print("\nStep 6: 验证 Redis 读取...")
try:
    df_loaded = redis_util.load_dataframe_by_key(f"{table_name}:{time_full}", use_compression=False)
    if df_loaded is not None and not df_loaded.empty:
        print(f"  OK: Redis read success, {len(df_loaded)} rows")
    else:
        print("  FAIL: Redis data empty")
except Exception as e:
    print(f"  FAIL: {e}")

print("\nAll tests completed!")
