#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import redis

try:
    client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # 获取注册表
    registry = client.smembers('process:registry')
    print(f"注册表中的进程ID: {len(registry)}")
    for pid in sorted(registry):
        print(f"  - {pid}")
    
    # 检查每个进程的详情
    print("\n\n进程详情:")
    for pid in sorted(registry):
        key = f'process:{pid}'
        key_type = client.type(key)
        print(f"\n{key} (类型: {key_type}):")
        
        if key_type == 'hash':
            data = client.hgetall(key)
            for k, v in data.items():
                print(f"  {k}: {v}")
        elif key_type == 'string':
            value = client.get(key)
            print(f"  值: {value[:100]}...")
        else:
            print(f"  未知类型")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
