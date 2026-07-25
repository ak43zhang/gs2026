# GS2026 内网穿透 - ngrok 停止逻辑
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
Write-Host "  GS2026 内网穿透 - 正在停止 ngrok..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$proc = Get-Process ngrok -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "[提示] 当前没有 ngrok 在运行，无需停止。" -ForegroundColor Gray
    Exit-Countdown 10
    exit 0
}

$proc | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

if (-not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "[成功] ngrok 已停止，外网访问已关闭。" -ForegroundColor Green
    Write-Host "局域网访问不受影响：http://192.168.0.102:8080"
} else {
    Write-Host "[警告] ngrok 可能未完全停止，请检查任务管理器。" -ForegroundColor Yellow
}

Exit-Countdown 10