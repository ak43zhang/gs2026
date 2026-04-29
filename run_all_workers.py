#!/usr/bin/env python3
"""
启动5个工作进程
"""
import subprocess
import sys
import time

print("=" * 60)
print("启动5个填充工作进程")
print("=" * 60)

processes = []
for i in range(1, 6):
    print(f"\n启动进程 {i}/5...")
    p = subprocess.Popen([
        sys.executable, 'fill_worker_final.py',
        str(i), '5'
    ], creationflags=subprocess.CREATE_NEW_CONSOLE)
    processes.append(p)
    time.sleep(2)

print("\n" + "=" * 60)
print("5个进程已启动！")
print("进程PID:", [p.pid for p in processes])
print("=" * 60)
print("\n等待所有进程完成...")

# 等待完成
for i, p in enumerate(processes, 1):
    p.wait()
    print(f"  进程 {i}/5 完成 (PID: {p.pid})")

print("\n" + "=" * 60)
print("全部完成！")
print("=" * 60)
