#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

# 测试债券上攻排行API - 使用历史时间
url = 'http://localhost:8080/api/monitor/attack-ranking/bond?date=20260414&time=13:38:51&limit=30'
req = urllib.request.Request(url)

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        items = data.get('data', [])
        
        # 查找美诺转债
        for item in items:
            if item.get('code') == '113618':
                print(f"找到美诺转债:")
                print(f"  code: {item.get('code')}")
                print(f"  name: {item.get('name')}")
                print(f"  is_realtime: {item.get('is_realtime')}")
                print(f"  count: {item.get('count')}")
                break
        else:
            print("美诺转债不在前30名中")
            
except Exception as e:
    print(f"Error: {e}")
