@echo off
chcp 65001 >nul
echo ==========================================
echo 启动5个填充工作进程
echo ==========================================

start "Worker 1/5" cmd /k "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_worker_final.py 1 5"
timeout /t 2 >nul

start "Worker 2/5" cmd /k "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_worker_final.py 2 5"
timeout /t 2 >nul

start "Worker 3/5" cmd /k "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_worker_final.py 3 5"
timeout /t 2 >nul

start "Worker 4/5" cmd /k "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_worker_final.py 4 5"
timeout /t 2 >nul

start "Worker 5/5" cmd /k "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_worker_final.py 5 5"

echo.
echo 5个进程已启动，请查看各个窗口的进度
echo ==========================================
pause
