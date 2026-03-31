#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深度分析 /api/monitor/attack-ranking/stock 接口调用链
"""
import time
import requests
from datetime import datetime

BASE_URL = 'http://localhost:8080'

print('=' * 80)
print('深度分析: /api/monitor/attack-ranking/stock')
print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 80)

# 1. 获取性能监控数据
print('\n1. 获取该接口的性能数据...')
try:
    resp = requests.get(f'{BASE_URL}/diag/performance', timeout=10)
    perf_data = resp.json()
    
    # 筛选该接口的慢请求
    stock_requests = [
        r for r in perf_data.get('slow_requests', [])
        if 'attack-ranking/stock' in r.get('path', '')
    ]
    
    print(f'  找到 {len(stock_requests)} 个慢请求')
    
    if stock_requests:
        print('\n  慢请求详情:')
        for i, req in enumerate(stock_requests[:5], 1):
            print(f'\n    {i}. 时间: {req.get("timestamp")}')
            print(f'       耗时: {req.get("duration_ms")}ms')
            print(f'       DB查询: {req.get("db_queries")}次, {req.get("db_time_ms")}ms')
            print(f'       Redis查询: {req.get("redis_queries")}次, {req.get("redis_time_ms")}ms')
            
            # 计算其他时间
            other_time = req.get('duration_ms', 0) - req.get('db_time_ms', 0) - req.get('redis_time_ms', 0)
            print(f'       其他时间: {other_time:.2f}ms (Python处理/序列化等)')
            
except Exception as e:
    print(f'  错误: {e}')

# 2. 实时测试并计时
print('\n2. 实时测试接口响应时间...')
endpoints = [
    ('/api/monitor/attack-ranking/stock?limit=60', '股票上攻排行(60条)'),
    ('/api/monitor/attack-ranking/stock?limit=30', '股票上攻排行(30条)'),
    ('/api/monitor/attack-ranking/stock?limit=10', '股票上攻排行(10条)'),
]

for endpoint, name in endpoints:
    try:
        start = time.time()
        resp = requests.get(f'{BASE_URL}{endpoint}', timeout=30)
        elapsed = (time.time() - start) * 1000
        
        data = resp.json()
        count = len(data.get('data', [])) if data.get('success') else 0
        
        print(f'\n  {name}:')
        print(f'    状态: {resp.status_code}')
        print(f'    总耗时: {elapsed:.2f}ms')
        print(f'    返回条数: {count}')
        
        # 检查响应头
        perf_header = resp.headers.get('X-Performance')
        if perf_header:
            print(f'    性能头: {perf_header}')
            
    except Exception as e:
        print(f'\n  {name}: 错误 - {e}')

# 3. 获取数据库慢查询
print('\n3. 获取数据库慢查询...')
try:
    resp = requests.get(f'{BASE_URL}/diag/db', timeout=10)
    db_data = resp.json()
    
    if db_data.get('enabled') and db_data.get('total_queries', 0) > 0:
        print(f"  总查询数: {db_data.get('total_queries')}")
        print(f"  平均耗时: {db_data.get('duration', {}).get('avg', 0):.2f}ms")
        
        recent_slow = db_data.get('recent_slow_queries', [])
        if recent_slow:
            print(f'\n  最近的慢查询:')
            for i, q in enumerate(recent_slow[:3], 1):
                print(f'\n    {i}. {q.get("duration_ms")}ms - {q.get("timestamp")}')
                stmt = q.get('statement', '')[:80]
                print(f'       {stmt}...')
    else:
        print('  暂无数据库查询数据')
except Exception as e:
    print(f'  错误: {e}')

print('\n' + '=' * 80)
print('分析完成')
print('=' * 80)
