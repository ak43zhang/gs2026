@echo off
chcp 65001 >nul
REM ============================================================
REM  GS2026 内网穿透 - ngrok 启动脚本
REM ============================================================
REM  作用：把本机 8080 端口的 Web 服务映射到外网，
REM        生成一个 https 网址，手机/异地电脑浏览器可直接访问。
REM
REM  使用方法：
REM    1. 确保 GS2026 Web 服务已启动（8080 端口在运行）
REM    2. 双击本脚本 启动ngrok.bat
REM    3. 稍等几秒，会自动弹出网址（也会打开 http://127.0.0.1:4040 查看）
REM    4. 把显示的 https://xxxx.ngrok-free.dev 网址发到手机即可访问
REM
REM  注意事项：
REM    - 免费版每次启动网址都会变，重启后需重新查看网址
REM    - 首次在手机打开会有 ngrok 蓝色警告页，点 "Visit Site" 进入
REM    - 本窗口关闭 或 运行"停止ngrok.bat" 即断开外网访问
REM    - 关闭后局域网 http://192.168.0.102:8080 访问不受影响
REM
REM  依赖：C:\ngrok\ngrok.exe（已配置 authtoken）
REM ============================================================

echo ============================================
echo   GS2026 内网穿透 - 正在启动 ngrok...
echo ============================================
echo.

REM 检查 ngrok 是否存在
if not exist "C:\ngrok\ngrok.exe" (
    echo [错误] 未找到 C:\ngrok\ngrok.exe
    echo 请先安装 ngrok 或联系管理员。
    pause
    exit /b 1
)

REM 检查 8080 Web 服务是否在运行
netstat -ano | findstr ":8080" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo [警告] 未检测到 8080 端口在监听！
    echo GS2026 Web 服务可能没启动，外网访问会打不开页面。
    echo.
    choice /c YN /m "是否仍要继续启动 ngrok"
    if errorlevel 2 exit /b 0
)

REM 先杀掉可能残留的 ngrok 进程，避免冲突
taskkill /f /im ngrok.exe >nul 2>&1
timeout /t 1 /nobreak >nul

echo 正在建立隧道，请稍候...
echo.

REM 后台启动 ngrok
start "" /min "C:\ngrok\ngrok.exe" http 8080

REM 等待隧道建立
timeout /t 6 /nobreak >nul

REM 通过本地 API 读取网址并显示
echo ============================================
powershell -NoProfile -Command "try { $t = (Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 8).tunnels; if($t.Count -gt 0){ Write-Host '  外网访问网址:' -NoNewline; Write-Host (' ' + $t[0].public_url) -ForegroundColor Green; Write-Host '  转发到本地:  ' $t[0].config.addr } else { Write-Host '  未获取到网址，请打开 http://127.0.0.1:4040 查看' } } catch { Write-Host '  读取网址失败，请手动打开 http://127.0.0.1:4040 查看' }"
echo ============================================
echo.
echo 提示：
echo   - 复制上面绿色网址发到手机浏览器打开
echo   - 首次访问点 "Visit Site" 跳过警告页
echo   - 关闭外网访问请运行 "停止ngrok.bat"
echo.

REM 打开本地控制台页面（可看网址、流量）
start "" http://127.0.0.1:4040

echo 按任意键关闭本窗口（ngrok 会继续在后台运行）...
pause >nul
