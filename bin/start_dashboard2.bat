@echo off
chcp 65001 >nul
cd /d F:\pyworkspace2026\gs2026
set PYTHONPATH=F:\pyworkspace2026\gs2026\src
python -c "from waitress import serve; from gs2026.dashboard2.app import create_app; serve(create_app(), host='0.0.0.0', port=5000)"
pause
