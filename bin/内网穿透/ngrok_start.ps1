# GS2026 内网穿透 - ngrok 启动逻辑（后台运行版）
$ErrorActionPreference = "Continue"
chcp 65001 > $null

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  GS2026 内网穿透 - 正在启动 ngrok..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$ngrok = "C:\ngrok\ngrok.exe"
if (-not (Test-Path $ngrok)) {
    Write-Host "[错误] 未找到 $ngrok" -ForegroundColor Red
    Write-Host "请先安装 ngrok 或联系管理员。"
    Read-Host "`n按回车键退出"
    exit 1
}

# 检查 8080 Web 服务
$has8080 = Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue
if (-not $has8080) {
    Write-Host "[警告] 未检测到 8080 端口在监听！" -ForegroundColor Yellow
    Write-Host "GS2026 Web 服务可能没启动，外网访问会打不开页面。"
    $ans = Read-Host "是否仍要继续启动 ngrok? (Y/N)"
    if ($ans -notmatch '^[Yy]') { exit 0 }
}

# 清理残留进程
Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "正在后台建立隧道，请稍候..." -ForegroundColor Gray

# 真后台运行：完全隐藏窗口，日志输出到文件
$logFile = "C:\ngrok\ngrok_runtime.log"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $ngrok
$psi.Arguments = "http 8080 --log=`"$logFile`" --log-format=logfmt"
$psi.WindowStyle = "Hidden"
$psi.CreateNoWindow = $true
$psi.UseShellExecute = $false
[System.Diagnostics.Process]::Start($psi) | Out-Null

Start-Sleep -Seconds 6

# 读取网址
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
$got = $false
for ($i=1; $i -le 4; $i++) {
    try {
        $t = (Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 8).tunnels
        if ($t.Count -gt 0) {
            Write-Host "  外网访问网址: " -NoNewline
            Write-Host $t[0].public_url -ForegroundColor Green
            Write-Host "  转发到本地:   $($t[0].config.addr)"
            $got = $true
            break
        }
    } catch { Start-Sleep -Seconds 3 }
}
if (-not $got) {
    Write-Host "  未获取到网址，请打开 http://127.0.0.1:4040 查看" -ForegroundColor Yellow
}
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "ngrok 已在后台运行（无窗口，日志: C:\ngrok\ngrok_runtime.log）" -ForegroundColor Gray
Write-Host ""
Write-Host "提示："
Write-Host "  - 复制上面绿色网址发到手机浏览器打开"
Write-Host "  - 首次访问点 `"Visit Site`" 跳过警告页"
Write-Host "  - 查看网址运行 查看网址.bat"
Write-Host "  - 关闭外网访问请运行 停止ngrok.bat"
Write-Host ""

# 打开本地控制台
Start-Process "http://127.0.0.1:4040"

Read-Host "按回车键关闭本窗口（ngrok 会继续在后台运行）"