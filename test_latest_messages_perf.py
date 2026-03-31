#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 /api/monitor/latest-messages 接口性能
"""
import time
import requests

print('测试 /api/monitor/latest-messages 接口性能')
print('=' * 50)

for i in range(3):
    start = time.time()
    resp = requests.get('http://localhost:8080/api/monitor/latest-messages?limit=50', timeout=30)
    elapsed = (time.time() - start) * 1000
    data = resp.json()
    count = len(data.get('data', []))
    print(f'请求{i+1}: 状态={resp.status_code}, 耗时={elapsed:.2f}ms, 条数={count}')

print('=' * 50)
print('优化完成！')
