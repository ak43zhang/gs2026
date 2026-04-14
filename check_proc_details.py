#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import redis

try:
    client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # 检查今天的开市采集进程
    today_procs = [
        'stock_20260414_5qfg',
        'bond_20260414_fr9m',
        'industry_20260414_z071',
        'dp_signal_20260414_k7b7',
        'gp_zq_signal_20260414_1rw0'
    ]
    
    print("今天的开市采集进程详细信息:")
    print("=" * 80)
    
    for proc_id in today_procs:
        key = f'process:{proc_id}'
        data = client.get(key)
        if data:
            info = json.loads(data)
            print(f"\n{proc_id}:")
            for k, v in info.items():
                print(f"  {k}: {v}")
            
except Exception as e:
    print(f"Error: {e}")
