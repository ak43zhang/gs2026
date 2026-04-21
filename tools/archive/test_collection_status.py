#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json

# 测试采集状态API
url = 'http://localhost:8080/api/collection/status'
req = urllib.request.Request(url)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f"Success: {data.get('success')}")
        processes = data.get('processes', [])
        print(f"\n找到 {len(processes)} 个进程")
        
        # 筛选开市采集相关的进程
        monitor_procs = [p for p in processes if 'stock' in p.get('process_id', '') or 
                                                  'bond' in p.get('process_id', '') or
                                                  'industry' in p.get('process_id', '') or
                                                  'dp_signal' in p.get('process_id', '') or
                                                  'gp_zq_signal' in p.get('process_id', '')]
        print(f"\n开市采集进程: {len(monitor_procs)}")
        for p in monitor_procs[:5]:
            print(f"  - {p.get('process_id')}: {p.get('status')} (PID: {p.get('pid')})")
            
except Exception as e:
    print(f"Error: {e}")
