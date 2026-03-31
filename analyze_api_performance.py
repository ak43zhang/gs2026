#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深度分析API慢请求 - 检查完整调用链
"""
import requests
import json
from datetime import datetime

BASE_URL = 'http://localhost:8080'

print('=' * 80)
print('API性能深度分析 - 慢请求调用链检查')
print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 80)

# 1. 获取API性能统计
print('\n1. 获取API性能统计...')
try:
    resp = requests.get(f'{BASE_URL}/diag/performance', timeout=10)
    perf_data = resp.json()
    
    if not perf_data.get('enabled'):
        print('  API性能监控未启用')
        exit(1)
    
    print(f"  总请求数: {perf_data.get('total_requests')}")
    print(f"  慢请求数: {perf_data.get('slow_requests', 0)}")
    print(f"  平均响应: {perf_data.get('duration', {}).get('avg', 0):.2f}ms")
    print(f"  P95响应: {perf_data.get('duration', {}).get('p95', 0):.2f}ms")
except Exception as e:
    print(f'  错误: {e}')
    exit(1)

# 2. 分析慢请求
print('\n2. 分析慢请求列表...')
slow_requests = perf_data.get('slow_requests', [])

if not slow_requests:
    print('  暂无慢请求数据')
    exit(0)

print(f'  找到 {len(slow_requests)} 个慢请求')

# 按端点分组
endpoint_stats = {}
for req in slow_requests:
    endpoint = req.get('endpoint', 'unknown')
    if endpoint not in endpoint_stats:
        endpoint_stats[endpoint] = []
    endpoint_stats[endpoint].append(req)

print('\n3. 按端点统计慢请求:')
for endpoint, reqs in sorted(endpoint_stats.items(), key=lambda x: -len(x[1])):
    durations = [r['duration_ms'] for r in reqs]
    avg = sum(durations) / len(durations)
    max_d = max(durations)
    min_d = min(durations)
    
    print(f'\n  {endpoint}')
    print(f'    次数: {len(reqs)}')
    print(f'    平均: {avg:.2f}ms')
    print(f'    最大: {max_d:.2f}ms')
    print(f'    最小: {min_d:.2f}ms')
    
    # 检查是否有DB/Redis时间数据
    has_db = any(r.get('db_time_ms', 0) > 0 for r in reqs)
    has_redis = any(r.get('redis_time_ms', 0) > 0 for r in reqs)
    
    if has_db:
        db_times = [r.get('db_time_ms', 0) for r in reqs if r.get('db_time_ms', 0) > 0]
        if db_times:
            print(f'    DB时间: {sum(db_times)/len(db_times):.2f}ms (平均)')
    
    if has_redis:
        redis_times = [r.get('redis_time_ms', 0) for r in reqs if r.get('redis_time_ms', 0) > 0]
        if redis_times:
            print(f'    Redis时间: {sum(redis_times)/len(redis_times):.2f}ms (平均)')

# 3. 分析具体慢请求
print('\n4. 详细分析最慢的请求:')
if slow_requests:
    slowest = sorted(slow_requests, key=lambda x: -x['duration_ms'])[0]
    print(f'\n  最慢请求:')
    print(f'    端点: {slowest.get("endpoint")}')
    print(f'    路径: {slowest.get("path")}')
    print(f'    耗时: {slowest.get("duration_ms")}ms')
    print(f'    时间: {slowest.get("timestamp")}')
    print(f'    DB查询: {slowest.get("db_queries", 0)} 次')
    print(f'    DB时间: {slowest.get("db_time_ms", 0)}ms')
    print(f'    Redis查询: {slowest.get("redis_queries", 0)} 次')
    print(f'    Redis时间: {slowest.get("redis_time_ms", 0)}ms')
    
    # 计算非DB/Redis时间
    other_time = slowest.get('duration_ms', 0) - slowest.get('db_time_ms', 0) - slowest.get('redis_time_ms', 0)
    print(f'    其他时间: {other_time:.2f}ms (Python处理/序列化/网络等)')

# 4. 获取数据库慢查询
print('\n5. 获取数据库慢查询统计...')
try:
    resp = requests.get(f'{BASE_URL}/diag/db', timeout=10)
    db_data = resp.json()
    
    if db_data.get('enabled') and db_data.get('total_queries', 0) > 0:
        print(f"  总查询数: {db_data.get('total_queries')}")
        print(f"  平均耗时: {db_data.get('duration', {}).get('avg', 0):.2f}ms")
        print(f"  最大耗时: {db_data.get('duration', {}).get('max', 0):.2f}ms")
        
        recent_slow = db_data.get('recent_slow_queries', [])
        if recent_slow:
            print(f'\n  最近的慢查询 ({len(recent_slow)}条):')
            for i, q in enumerate(recent_slow[:5], 1):
                print(f'\n    {i}. {q.get("duration_ms")}ms')
                stmt = q.get('statement', '')[:100]
                print(f'       SQL: {stmt}...')
    else:
        print('  暂无数据库查询数据')
except Exception as e:
    print(f'  错误: {e}')

# 5. 测试API响应时间
print('\n6. 实时测试API响应时间...')
api_tests = [
    ('/api/monitor/attack-ranking/stock?limit=60', '股票上攻排行'),
    ('/api/monitor/latest-messages', '最新消息'),
    ('/api/monitor/combine-ranking?limit=50', '股债联动排行'),
]

for endpoint, name in api_tests:
    try:
        import time
        start = time.time()
        resp = requests.get(f'{BASE_URL}{endpoint}', timeout=30)
        elapsed = (time.time() - start) * 1000
        
        print(f'\n  {name}:')
        print(f'    状态: {resp.status_code}')
        print(f'    耗时: {elapsed:.2f}ms')
        
        # 检查响应头中是否有性能信息
        perf_header = resp.headers.get('X-Performance')
        if perf_header:
            print(f'    性能头: {perf_header}')
            
    except Exception as e:
        print(f'\n  {name}: 错误 - {e}')

print('\n' + '=' * 80)
print('分析完成')
print('=' * 80)
