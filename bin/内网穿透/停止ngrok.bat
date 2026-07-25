@echo off
REM GS2026 neiwang chuantou - stop ngrok
REM Double-click to close external access.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ngrok_stop.ps1"