@echo off
chcp 65001 >nul
REM ============================================================
REM  GS2026 内网穿透 - 查看当前外网网址
REM ============================================================
REM  作用：查看 ngrok 当前的外网访问网址和运行状态。
REM
REM  使用方法：
REM    双击本脚本 查看网址.bat
REM
REM  适用场景：
REM    - 忘记了外网网址（ngrok 每次重启网址都变）
REM    - 想确认 ngrok 是否还在运行
REM ============================================================

echo ============================================
echo   GS2026 内网穿透 - 当前状态
echo ============================================
echo.

REM 检查 ngrok 进程
tasklist /fi "imagename eq ngrok.exe" | findstr /i "ngrok.exe" >nul
if errorlevel 1 (
    echo [状态] ngrok 未运行
    echo 要开启外网访问，请运行 "启动ngrok.bat"
    echo.
    pause
    exit /b 0
)

echo [状态] ngrok 运行中
echo.

REM 读取并显示网址
powershell -NoProfile -Command "try { $t = (Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 8).tunnels; if($t.Count -gt 0){ Write-Host '  外网访问网址:' -NoNewline; Write-Host (' ' + $t[0].public_url) -ForegroundColor Green; Write-Host '  转发到本地:   ' $t[0].config.addr } else { Write-Host '  隧道未就绪，请打开 http://127.0.0.1:4040 查看' } } catch { Write-Host '  读取失败，请手动打开 http://127.0.0.1:4040' }"

echo.
echo ============================================
echo 提示：也可浏览器打开 http://127.0.0.1:4040 查看详细流量
echo.
pause
