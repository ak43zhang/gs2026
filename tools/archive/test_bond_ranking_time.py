#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

# 测试债券上攻排行API - 使用历史时间
url = 'http://localhost:8080/api/monitor/attack-ranking/bond?date=20260414&time=13:38:51&limit=10'
req = urllib.request.Request(url)

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f"Success: {data.get('success')}")
        items = data.get('data', [])
        print(f"\n返回 {len(items)} 条数据")
        
        realtime_count = sum(1 for item in items if item.get('is_realtime'))
        print(f"实时数据: {realtime_count} 条")
        
        for i, item in enumerate(items[:10]):
            rt_mark = "[实]" if item.get('is_realtime') else "   "
            print(f"{i+1}. {rt_mark} {item.get('code')} {item.get('name')} - count:{item.get('count')}")
            
except Exception as e:
    print(f"Error: {e}")
