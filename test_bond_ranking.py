#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

# 测试债券上攻排行API
url = 'http://localhost:8080/api/monitor/attack-ranking/bond?date=20260414&limit=5'
req = urllib.request.Request(url)

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f"Success: {data.get('success')}")
        items = data.get('data', [])
        print(f"\n返回 {len(items)} 条数据")
        
        for i, item in enumerate(items[:5]):
            print(f"\n{i+1}. {item.get('code')} {item.get('name')}")
            print(f"   count: {item.get('count')}")
            print(f"   is_realtime: {item.get('is_realtime')}")
            print(f"   is_green: {item.get('is_green')}")
            print(f"   change_pct: {item.get('change_pct')}")
            
except Exception as e:
    print(f"Error: {e}")
