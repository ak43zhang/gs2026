#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import json

BASE_URL = 'http://localhost:8080'

print('=' * 60)
print('DBProfiler 问题排查')
print('=' * 60)

print('\n1. 检查 /diag/db 端点...')
try:
    resp = requests.get(f'{BASE_URL}/diag/db', timeout=5)
    print('状态码:', resp.status_code)
    data = resp.json()
    print('enabled:', data.get('enabled'))
    print('total_queries:', data.get('total_queries'))
    print('message:', data.get('message'))
except Exception as e:
    print('错误:', e)

print('\n2. 触发数据库查询...')
try:
    resp = requests.get(f'{BASE_URL}/attack-ranking/stock?limit=10', timeout=10)
    print('股票排行API状态码:', resp.status_code)
except Exception as e:
    print('错误:', e)

print('\n3. 再次检查DB统计...')
try:
    resp = requests.get(f'{BASE_URL}/diag/db', timeout=5)
    data = resp.json()
    print('enabled:', data.get('enabled'))
    print('total_queries:', data.get('total_queries'))
    print('message:', data.get('message'))
except Exception as e:
    print('错误:', e)

print('\n' + '=' * 60)
