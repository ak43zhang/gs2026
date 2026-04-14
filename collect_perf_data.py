#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收集性能诊断数据
"""
import requests
import json
from datetime import datetime

BASE_URL = 'http://localhost:8080'

print('=' * 70)
print('性能诊断数据收集')
print('=' * 70)

results = {
    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'api_performance': None,
    'db_stats': None,
    'slow_requests': None,
    'slow_queries': None
}

# 1. API性能统计
print('\n1. 收集API性能统计...')
try:
    resp = requests.get(f'{BASE_URL}/diag/performance', timeout=10)
    if resp.status_code == 200:
        results['api_performance'] = resp.json()
        print('   成功')
    else:
        print(f'   状态码: {resp.status_code}')
except Exception as e:
    print(f'   错误: {e}')

# 2. 数据库查询统计
print('\n2. 收集数据库查询统计...')
try:
    resp = requests.get(f'{BASE_URL}/diag/db', timeout=10)
    if resp.status_code == 200:
        results['db_stats'] = resp.json()
        print('   成功')
    else:
        print(f'   状态码: {resp.status_code}')
except Exception as e:
    print(f'   错误: {e}')

# 3. 触发几个慢API并记录时间
print('\n3. 测试API响应时间...')
api_tests = [
    ('/attack-ranking/stock?limit=60', '股票上攻排行'),
    ('/api/monitor/combine-ranking?limit=50', '股债联动排行'),
    ('/api/monitor/bond-ranking?limit=60', '债券排行'),
]

api_times = []
for endpoint, name in api_tests:
    try:
        import time
        start = time.time()
        resp = requests.get(f'{BASE_URL}{endpoint}', timeout=30)
        elapsed = (time.time() - start) * 1000
        api_times.append({
            'name': name,
            'endpoint': endpoint,
            'status': resp.status_code,
            'time_ms': round(elapsed, 2)
        })
        print(f'   {name}: {elapsed:.2f}ms')
    except Exception as e:
        print(f'   {name}: 错误 - {e}')

results['api_tests'] = api_times

# 4. 再次收集统计数据
print('\n4. 再次收集统计数据...')
try:
    resp = requests.get(f'{BASE_URL}/diag/performance', timeout=10)
    if resp.status_code == 200:
        results['api_performance_after'] = resp.json()
except Exception as e:
    print(f'   API性能: {e}')

try:
    resp = requests.get(f'{BASE_URL}/diag/db', timeout=10)
    if resp.status_code == 200:
        results['db_stats_after'] = resp.json()
except Exception as e:
    print(f'   DB统计: {e}')

# 保存结果
print('\n5. 保存诊断数据...')
with open('perf_diagnosis_data.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print('   已保存到 perf_diagnosis_data.json')

# 输出摘要
print('\n' + '=' * 70)
print('诊断摘要')
print('=' * 70)

if results['api_performance']:
    perf = results['api_performance']
    print(f"\nAPI性能监控:")
    print(f"  启用状态: {perf.get('enabled')}")
    print(f"  总请求数: {perf.get('total_requests')}")
    print(f"  慢请求数: {perf.get('slow_requests')}")

if results['db_stats']:
    db = results['db_stats']
    print(f"\n数据库查询统计:")
    print(f"  启用状态: {db.get('enabled')}")
    print(f"  总查询数: {db.get('total_queries')}")
    print(f"  消息: {db.get('message')}")

print(f"\nAPI响应时间测试:")
for test in api_times:
    print(f"  {test['name']}: {test['time_ms']}ms")

print('\n' + '=' * 70)
