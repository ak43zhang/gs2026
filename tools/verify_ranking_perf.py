"""Verify stock ranking optimization - simulate Flask context"""
import sys, time
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

# Pre-import to simulate warm Flask app
from gs2026.utils import redis_util
try:
    redis_util.init_redis()
except:
    pass

from gs2026.dashboard.services.data_service import DataService
from gs2026.dashboard2.routes.monitor import (
    _get_shared_engine, get_cached_sssj_df, _get_latest_sssj_time,
    _enrich_stock_data, _enrich_change_pct_and_main_net
)

ds = DataService()
date = '20260518'

print("=== 优化后性能验证 ===\n")

# Warm up run
print("--- Warm-up (首次请求) ---")
t0 = time.time()
data = ds.get_stock_ranking(limit=60, date=date, use_mysql=True)
t1 = time.time()
print(f"1. get_stock_ranking: {(t1-t0)*1000:.0f}ms ({len(data)} items)")

t2 = time.time()
data = _enrich_stock_data(data)
t3 = time.time()
print(f"2. enrich_stock_data: {(t3-t2)*1000:.0f}ms")

t4 = time.time()
data = _enrich_change_pct_and_main_net(data, date)
t5 = time.time()
print(f"3. enrich_change_pct: {(t5-t4)*1000:.0f}ms")

total1 = (t5-t0)*1000
print(f"   总计: {total1:.0f}ms\n")

# Second run (cache warm)
print("--- 第二次请求 (缓存命中) ---")
data2 = ds.get_stock_ranking(limit=60, date=date, use_mysql=True)

t6 = time.time()
data2 = _enrich_stock_data(data2)
t7 = time.time()
print(f"2. enrich_stock_data: {(t7-t6)*1000:.0f}ms")

t8 = time.time()
data2 = _enrich_change_pct_and_main_net(data2, date)
t9 = time.time()
print(f"3. enrich_change_pct: {(t9-t8)*1000:.0f}ms")

total2 = (t9-t6)*1000
print(f"   总计: {total2:.0f}ms\n")

# Third run - limit=500
print("--- limit=500 (最大) ---")
data3 = ds.get_stock_ranking(limit=500, date=date, use_mysql=True)

t10 = time.time()
data3 = _enrich_stock_data(data3)
t11 = time.time()
print(f"2. enrich_stock_data: {(t11-t10)*1000:.0f}ms ({len(data3)} items)")

t12 = time.time()
data3 = _enrich_change_pct_and_main_net(data3, date)
t13 = time.time()
print(f"3. enrich_change_pct: {(t13-t12)*1000:.0f}ms")

total3 = (t13-t10)*1000
print(f"   总计: {total3:.0f}ms\n")

print(f"=== 结果 ===")
print(f"首次请求: {total1:.0f}ms")
print(f"缓存命中: {total2:.0f}ms")
print(f"limit=500: {total3:.0f}ms")
