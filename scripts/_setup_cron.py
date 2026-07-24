# -*- coding: utf-8 -*-
"""
设置定时任务：每天开盘前自动刷新TDX IP池

Windows Task Scheduler 命令
"""
import os
import subprocess

# 配置
TASK_NAME = "GS2026_TDX_IP_Refresh"
PYTHON_EXE = r"F:\pyworkspace2026\gs2026\.venv\Scripts\python.exe"
SCRIPT_PATH = r"F:\pyworkspace2026\gs2026\scripts\refresh_tdx_ips.py"
WORKING_DIR = r"F:\pyworkspace2026\gs2026"

# 创建任务（每天 08:50 运行，早于9:30开盘）
# 使用 schtasks 命令
cmd = [
    "schtasks", "/create", "/tn", TASK_NAME,
    "/tr", f'"{PYTHON_EXE}" "{SCRIPT_PATH}"',
    "/sc", "daily",
    "/st", "08:50",
    "/ru", "SYSTEM",
    "/f"  # 强制覆盖已存在的任务
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='gbk', errors='ignore')
    if result.returncode == 0:
        print(f"TASK_CREATED_OK: {TASK_NAME}")
        print("Schedule: Daily 08:50")
        print(f"Command: {PYTHON_EXE} {SCRIPT_PATH}")
    else:
        print(f"TASK_CREATE_FAIL: {result.returncode}")
        print(f"stderr: {result.stderr}")
except Exception as e:
    print(f"EXCEPTION: {e}")

# 验证任务创建
try:
    verify = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME], 
                            capture_output=True, text=True, encoding='gbk', errors='ignore')
    if verify.returncode == 0:
        print(f"TASK_VERIFIED: {TASK_NAME}")
    else:
        print(f"TASK_VERIFY_FAIL")
except Exception as e:
    print(f"VERIFY_EXCEPTION: {e}")
