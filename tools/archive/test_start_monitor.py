#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json
import time
import psutil

# 启动股票监控
url = 'http://localhost:8080/api/collection/monitor/start/stock'
req = urllib.request.Request(url, method='POST', 
                             headers={'Content-Type': 'application/json'},
                             data=json.dumps({}).encode())

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(f"启动结果: {data}")
        
        if data.get('success'):
            pid = data.get('pid')
            print(f"进程PID: {pid}")
            
            # 监控30秒
            print("\n监控进程状态...")
            for i in range(30):
                time.sleep(1)
                try:
                    p = psutil.Process(pid)
                    if p.is_running():
                        print(f"[{i+1}s] 进程运行中 (PID: {pid})")
                    else:
                        print(f"[{i+1}s] 进程已停止!")
                        break
                except psutil.NoSuchProcess:
                    print(f"[{i+1}s] 进程不存在!")
                    break
        else:
            print(f"启动失败: {data.get('error')}")
            
except Exception as e:
    print(f"Error: {e}")
