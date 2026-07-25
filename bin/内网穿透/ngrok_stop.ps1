# GS2026 内网穿透 - ngrok 停止逻辑
chcp 65001 > $null

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  GS2026 内网穿透 - 正在停止 ngrok..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$proc = Get-Process ngrok -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "[提示] 当前没有 ngrok 在运行，无需停止。" -ForegroundColor Gray
    Read-Host "`n按回车键退出"
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
Write-Host ""
Read-Host "按回车键退出"