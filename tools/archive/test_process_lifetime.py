#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import time
import psutil

# 启动一个测试进程并监控
print("启动测试进程...")

import subprocess
proc = subprocess.Popen(
    [r'F:\python312\python.exe', '-c', 'import time; print("Started"); time.sleep(60)'],
    cwd=r'F:\pyworkspace2026\gs2026'
)

print(f"测试进程PID: {proc.pid}")

# 监控30秒
for i in range(30):
    time.sleep(1)
    try:
        p = psutil.Process(proc.pid)
        if p.is_running():
            print(f"[{i+1}s] 进程仍在运行 (PID: {proc.pid})")
        else:
            print(f"[{i+1}s] 进程已停止!")
            break
    except psutil.NoSuchProcess:
        print(f"[{i+1}s] 进程不存在!")
        break

print("监控结束")
