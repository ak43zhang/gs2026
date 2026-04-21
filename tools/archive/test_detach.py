#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试子进程是否在父进程关闭后继续运行
"""
import subprocess
import time
import sys
import os

# 测试脚本 - 子进程会运行30秒
test_script = '''
import time
import os
print(f"子进程启动 PID: {os.getpid()}")
for i in range(30):
    print(f"子进程运行中... {i+1}/30")
    time.sleep(1)
print("子进程结束")
'''

# 保存测试脚本
with open('test_child.py', 'w') as f:
    f.write(test_script)

print(f"父进程 PID: {os.getpid()}")
print("启动子进程...")

# 方式1: 使用DETACHED_PROCESS（当前实现方式）
proc = subprocess.Popen(
    [sys.executable, 'test_child.py'],
    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

print(f"子进程已启动 PID: {proc.pid}")
print("父进程即将退出，观察子进程是否继续运行...")
print(f"请在命令行运行: tasklist | findstr {proc.pid}")
