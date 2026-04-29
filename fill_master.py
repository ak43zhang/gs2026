#!/usr/bin/env python3
"""
主控脚本 - 启动5个工作进程并行填充
"""
import subprocess
import sys
import time

print("=" * 60)
print("并行填充主控 - 5000只股票分5进程")
print("=" * 60)

start_time = time.time()

# 启动5个工作进程
processes = []
for i in range(5):
    worker_id = i + 1
    print(f"\n启动工作进程 {worker_id}/5...")
    
    p = subprocess.Popen([
        sys.executable, 'fill_worker.py', 
        str(worker_id),
        str(5)
    ])
    processes.append(p)

print(f"\n所有工作进程已启动，等待完成...")
print(f"进程列表: {[p.pid for p in processes]}")

# 等待所有进程完成
for i, p in enumerate(processes, 1):
    p.wait()
    print(f"  进程 {i}/5 完成 (PID: {p.pid})")

elapsed = time.time() - start_time
print(f"\n{'='*60}")
print(f"全部完成! 总用时: {elapsed/60:.1f} 分钟")
