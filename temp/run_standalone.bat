@echo off
cd /d F:\pyworkspace2026\gs2026
F:\python312\python.exe temp\test_news_cls_standalone.py > F:\pyworkspace2026\gs2026\logs\analysis\standalone_cmd.log 2>&1
echo Exit code: %ERRORLEVEL% >> F:\pyworkspace2026\gs2026\logs\analysis\standalone_cmd.log
