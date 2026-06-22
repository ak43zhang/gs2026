@echo off
echo 停止 monitor_stock.py...
taskkill /f /im python.exe 2>nul
timeout /t 3

echo 启动 monitor_stock.py...
cd /d F:\pyworkspace2026\gs2026
.venv\Scripts\python.exe -m gs2026.monitor.monitor_stock

echo 启动完成
pause
