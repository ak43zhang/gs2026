# GS2026 内网穿透 - 查看网址逻辑
chcp 65001 > $null

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  GS2026 内网穿透 - 当前状态" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "[状态] ngrok 未运行" -ForegroundColor Yellow
    Write-Host "要开启外网访问，请运行 启动ngrok.bat"
    Read-Host "`n按回车键退出"
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
Write-Host ""
Read-Host "按回车键退出"