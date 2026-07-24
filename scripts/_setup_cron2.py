# -*- coding: utf-8 -*-
"""
设置定时任务 v2：使用当前用户而非SYSTEM
"""
import os
import subprocess

TASK_NAME = "GS2026_TDX_IP_Refresh"
PYTHON_EXE = r"F:\pyworkspace2026\gs2026\.venv\Scripts\python.exe"
SCRIPT_PATH = r"F:\pyworkspace2026\gs2026\scripts\refresh_tdx_ips.py"

# 删除旧任务（如果存在）
subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"], 
               capture_output=True, encoding='gbk', errors='ignore')

# 创建新任务 - 使用当前用户，不指定密码（交互式）
cmd = [
    "schtasks", "/create", "/tn", TASK_NAME,
    "/tr", f'"{PYTHON_EXE}" "{SCRIPT_PATH}"',
    "/sc", "daily",
    "/st", "08:50",
    "/f"
]

try:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='gbk', errors='ignore')
    print(f"EXIT={result.returncode}")
    if result.stdout:
        print(f"OUT={result.stdout.strip()}")
    if result.stderr:
        print(f"ERR={result.stderr.strip()}")
except Exception as e:
    print(f"EXC={e}")

# 查询验证
try:
    v = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME, "/fo", "LIST"], 
                       capture_output=True, text=True, encoding='gbk', errors='ignore')
    if v.returncode == 0 and TASK_NAME in v.stdout:
        print(f"VERIFIED={TASK_NAME}")
    else:
        print("VERIFY_FAIL")
except Exception as e:
    print(f"VEXC={e}")
