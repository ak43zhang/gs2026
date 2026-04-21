#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util

try:
    redis_util.init_redis(host='localhost', port=6379, decode_responses=True)
    client = redis_util._get_redis_client()
    
    # 获取所有进程相关的key
    keys = client.keys('process:*')
    print(f"找到 {len(keys)} 个进程记录")
    
    for key in sorted(keys):
        data = client.hgetall(key)
        print(f"\n{key}:")
        for k, v in data.items():
            print(f"  {k}: {v}")
            
    # 检查监控服务状态
    monitor_keys = client.keys('monitor:*')
    print(f"\n\n找到 {len(monitor_keys)} 个监控记录")
    for key in sorted(monitor_keys):
        print(f"  {key}")
        
except Exception as e:
    print(f"Error: {e}")
