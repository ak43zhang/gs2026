#!/usr/bin/env python3
"""直接调用API，传入指定时间点，验证API是否能正确匹配"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import requests
import json

API_BASE = 'http://localhost:8080/api/monitor'

print("=" * 60)
print("测试API在指定时间点是否能命中")
print("=" * 60)

# 测试1: 不传时间（取最新tick）
print("\n[测试1] 不传时间参数（取最新tick）")
try:
    r = requests.post(f'{API_BASE}/quant-screen', json={}, timeout=10)
    data = r.json()
    print(f"  状态码: {r.status_code}")
    print(f"  success: {data.get('success')}")
    print(f"  time: {data.get('time')}")
    print(f"  matches数: {len(data.get('matches', []))}")
    print(f"  stats: {data.get('stats')}")
    if data.get('message'):
        print(f"  message: {data['message']}")
    if data.get('error'):
        print(f"  error: {data['error']}")
    if data.get('schemes'):
        print(f"  方案数: {len(data['schemes'])}")
        for s in data['schemes']:
            print(f"    - {s.get('name')}")
except Exception as e:
    print(f"  ✗ 请求失败: {e}")

# 测试2: 传入10:42:48（已知有命中的时间点）
print("\n[测试2] 传入 time=104248（已知123195应该命中）")
try:
    r = requests.post(f'{API_BASE}/quant-screen', 
                     json={'time': '104248'}, timeout=10)
    data = r.json()
    print(f"  状态码: {r.status_code}")
    print(f"  success: {data.get('success')}")
    print(f"  time: {data.get('time')}")
    print(f"  matches数: {len(data.get('matches', []))}")
    print(f"  stats: {data.get('stats')}")
    if data.get('matches'):
        print(f"  命中列表:")
        for m in data['matches'][:5]:
            print(f"    {m.get('bond_code')} {m.get('bond_name')} "
                  f"price={m.get('price')} change={m.get('change_pct')}%")
    if data.get('message'):
        print(f"  message: {data['message']}")
    if data.get('error'):
        print(f"  error: {data['error']}")
except Exception as e:
    print(f"  ✗ 请求失败: {e}")

# 测试3: 传入10:42:48（带冒号格式）
print("\n[测试3] 传入 time=10:42:48（带冒号格式）")
try:
    r = requests.post(f'{API_BASE}/quant-screen', 
                     json={'time': '10:42:48'}, timeout=10)
    data = r.json()
    print(f"  状态码: {r.status_code}")
    print(f"  success: {data.get('success')}")
    print(f"  time: {data.get('time')}")
    print(f"  matches数: {len(data.get('matches', []))}")
    print(f"  stats: {data.get('stats')}")
    if data.get('matches'):
        print(f"  命中列表:")
        for m in data['matches'][:5]:
            print(f"    {m.get('bond_code')} {m.get('bond_name')} "
                  f"price={m.get('price')} change={m.get('change_pct')}%")
except Exception as e:
    print(f"  ✗ 请求失败: {e}")

# 测试4: 检查服务端日志（看有没有报错）
print("\n[测试4] 检查quant_screen_hits是否新增了记录")
from sqlalchemy import create_engine, text
engine = create_engine("mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT COUNT(*) FROM quant_screen_hits WHERE trade_date = '20260710'
    """))
    count = result.fetchone()[0]
    print(f"  今日总命中记录: {count}")

print("\n" + "=" * 60)
