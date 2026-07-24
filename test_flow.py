# -*- coding: utf-8 -*-
"""测试完整自动化流程"""

import requests
import time

BASE = 'http://127.0.0.1:8081'

# 步骤1: 发送命中
print('=== 步骤1: 发送命中 ===')
r = requests.post(f'{BASE}/api/auto_trade/hit', json={
    'code': '113052',
    'name': '兴业转债',
    'price': 115.5,
    'scheme': {'name': '测试方案', 'take_profit': 3.0, 'stop_loss': 2.0, 'max_hold_time': 30},
    'lots': 1
})
print('Hit response:', r.json())

# 步骤2: 检查状态
print('\n=== 步骤2: 检查状态 ===')
r = requests.get(f'{BASE}/api/auto_trade/status')
data = r.json()
print('State:', data.get('state'))
print('Mode:', data.get('mode'))
print('Hit list count:', len(data.get('hit_list', [])))
for h in data.get('hit_list', []):
    print('  Hit:', h.get('code'), h.get('name'))

# 步骤3: 点击买入
print('\n=== 步骤3: 点击买入 ===')
r = requests.post(f'{BASE}/api/auto_trade/buy/113052')
print('Buy response:', r.json())

# 步骤4: 再次检查状态
print('\n=== 步骤4: 再次检查状态 ===')
r = requests.get(f'{BASE}/api/auto_trade/status')
data = r.json()
print('State:', data.get('state'))
print('Current:', data.get('current'))
print('Mode:', data.get('mode'))
