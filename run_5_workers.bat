@echo off
echo ==========================================
echo Starting 5 workers
echo ==========================================

start "Worker 1" cmd /c "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_single_worker.py 1 5 > worker1.log 2>&1"
timeout /t 2 /nobreak >nul

start "Worker 2" cmd /c "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_single_worker.py 2 5 > worker2.log 2>&1"
timeout /t 2 /nobreak >nul

start "Worker 3" cmd /c "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_single_worker.py 3 5 > worker3.log 2>&1"
timeout /t 2 /nobreak >nul

start "Worker 4" cmd /c "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_single_worker.py 4 5 > worker4.log 2>&1"
timeout /t 2 /nobreak >nul

start "Worker 5" cmd /c "cd /d F:\pyworkspace2026\gs2026 && .venv\Scripts\python.exe fill_single_worker.py 5 5 > worker5.log 2>&1"

echo.
echo All 5 workers started
echo Check worker*.log files for progress
echo ==========================================
