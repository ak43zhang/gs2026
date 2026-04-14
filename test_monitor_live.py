#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import subprocess
import time
import psutil

print("启动股票监控进程...")

proc = subprocess.Popen(
    [r'F:\python312\python.exe', r'F:\pyworkspace2026\gs2026\src\gs2026\monitor\monitor_stock.py'],
    cwd=r'F:\pyworkspace2026\gs2026',
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

print(f"进程PID: {proc.pid}")

# 监控30秒
for i in range(30):
    time.sleep(1)
    
    # 检查进程状态
    try:
        p = psutil.Process(proc.pid)
        if p.is_running():
            cpu = p.cpu_percent()
            mem = p.memory_info().rss / 1024 / 1024
            print(f"[{i+1}s] PID {proc.pid} 运行中 - CPU: {cpu:.1f}%, 内存: {mem:.1f}MB")
        else:
            print(f"[{i+1}s] 进程已停止!")
            # 读取输出
            stdout, stderr = proc.communicate(timeout=5)
            print(f"stdout: {stdout.decode('utf-8', errors='ignore')[-500:]}")
            print(f"stderr: {stderr.decode('utf-8', errors='ignore')[-500:]}")
            break
    except psutil.NoSuchProcess:
        print(f"[{i+1}s] 进程不存在!")
        stdout, stderr = proc.communicate(timeout=5)
        print(f"stdout: {stdout.decode('utf-8', errors='ignore')[-500:]}")
        print(f"stderr: {stderr.decode('utf-8', errors='ignore')[-500:]}")
        break
    except Exception as e:
        print(f"[{i+1}s] 错误: {e}")

print("\n监控结束")
