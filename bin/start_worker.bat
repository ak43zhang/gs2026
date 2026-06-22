@echo off
chcp 65001 >nul
echo 启动工作进程 %1/5...
cd /d F:\pyworkspace2026\gs2026
.venv\Scripts\python.exe fill_worker_final.py %1 5
pause
