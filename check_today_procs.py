#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import json
import redis
import psutil

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
    
    print("今天的开市采集进程状态:")
    print("=" * 80)
    
    for proc_id in today_procs:
        key = f'process:{proc_id}'
        data = client.get(key)
        if data:
            info = json.loads(data)
            pid = info.get('pid')
            status = info.get('status')
            
            # 检查进程是否真实存在
            running = False
            if pid:
                try:
                    proc = psutil.Process(pid)
                    running = proc.is_running() and proc.name().lower() == 'python.exe'
                except psutil.NoSuchProcess:
                    running = False
            
            print(f"\n{proc_id}:")
            print(f"  PID: {pid}")
            print(f"  Redis状态: {status}")
            print(f"  实际运行: {running}")
            print(f"  服务ID: {info.get('service_id')}")
            print(f"  进程类型: {info.get('process_type')}")
        else:
            print(f"\n{proc_id}: 无Redis记录")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
