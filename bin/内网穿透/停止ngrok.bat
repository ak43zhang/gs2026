@echo off
chcp 65001 >nul
REM ============================================================
REM  GS2026 内网穿透 - ngrok 停止脚本
REM ============================================================
REM  作用：关闭 ngrok 隧道，断开外网访问，恢复纯局域网状态。
REM
REM  使用方法：
REM    1. 双击本脚本 停止ngrok.bat
REM    2. 看到"已停止"即完成
REM
REM  停止后：
REM    - 外网网址立即失效，外部再也访问不到
REM    - 局域网 http://192.168.0.102:8080 访问完全不受影响
REM    - 下次要用外网，重新运行 "启动ngrok.bat"（网址会变）
REM ============================================================

echo ============================================
echo   GS2026 内网穿透 - 正在停止 ngrok...
echo ============================================
echo.

REM 检查是否有 ngrok 在运行
tasklist /fi "imagename eq ngrok.exe" | findstr /i "ngrok.exe" >nul
if errorlevel 1 (
    echo [提示] 当前没有 ngrok 在运行，无需停止。
    echo.
    pause
    exit /b 0
)

REM 杀掉所有 ngrok 进程
taskkill /f /im ngrok.exe >nul 2>&1

timeout /t 1 /nobreak >nul

REM 验证是否已停止
tasklist /fi "imagename eq ngrok.exe" | findstr /i "ngrok.exe" >nul
if errorlevel 1 (
    echo [成功] ngrok 已停止，外网访问已关闭。
    echo 局域网访问不受影响：http://192.168.0.102:8080
) else (
    echo [警告] ngrok 可能未完全停止，请检查任务管理器。
)

echo.
pause
