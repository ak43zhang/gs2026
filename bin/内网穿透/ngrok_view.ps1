# GS2026 内网穿透 - 查看网址逻辑
chcp 65001 > $null

function Exit-Countdown {
    param([int]$Seconds = 10)
    Write-Host ""
    for ($s = $Seconds; $s -gt 0; $s--) {
        Write-Host "`r本窗口将在 $s 秒后自动关闭...（按任意键立即关闭）  " -NoNewline -ForegroundColor Gray
        try {
            if ([System.Console]::KeyAvailable) { [System.Console]::ReadKey($true) | Out-Null; break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    Write-Host ""
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  GS2026 内网穿透 - 当前状态" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "[状态] ngrok 未运行" -ForegroundColor Yellow
    Write-Host "要开启外网访问，请运行 启动ngrok.bat"
    Exit-Countdown 10
    exit 0
}

Write-Host "[状态] ngrok 运行中" -ForegroundColor Green
Write-Host ""
try {
    $t = (Invoke-RestMethod 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 8).tunnels
    if ($t.Count -gt 0) {
        Write-Host "  外网访问网址: " -NoNewline
        Write-Host $t[0].public_url -ForegroundColor Green
        Write-Host "  转发到本地:   $($t[0].config.addr)"
    } else {
        Write-Host "  隧道未就绪，请打开 http://127.0.0.1:4040 查看" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  读取失败，请手动打开 http://127.0.0.1:4040" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "============================================"
Write-Host "提示：也可浏览器打开 http://127.0.0.1:4040 查看详细流量"

Exit-Countdown 10