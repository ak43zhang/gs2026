# Flask 服务运维手册

## 服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户浏览器                           │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────────┐
│                   Nginx (可选)                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   Flask App (5000端口)                      │
│  ┌──────────────┬──────────────┬──────────────┐            │
│  │ 股票排行接口  │ 债券排行接口  │ 行业排行接口  │            │
│  └──────────────┴──────────────┴──────────────┘            │
└──────────────────────┬──────────────────────────────────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
┌──────────▼──────────┐  ┌────────▼────────┐
│       Redis         │  │      MySQL      │
│  (实时数据缓存)      │  │   (历史数据)     │
└─────────────────────┘  └─────────────────┘
```

---

## 启动服务

### 开发环境

```bash
cd F:\pyworkspace2026\gs2026
.\.venv\Scripts\python.exe src\gs2026\dashboard2\app.py
```

### 生产环境（后台运行）

```bash
cd F:\pyworkspace2026\gs2026
# 使用 nohup 或 pm2
start /B .\.venv\Scripts\python.exe src\gs2026\dashboard2\app.py > logs\flask.log 2>&1
```

---

## 检查服务状态

### 查看进程

```powershell
# 查看 Python 进程
Get-Process python* | Select-Object Id, ProcessName, StartTime

# 查看 Flask 端口占用
netstat -ano | findstr :5000
```

### 健康检查

```bash
# 检查 API 是否正常
curl http://localhost:5000/api/health

# 检查股票排行
curl http://localhost:5000/api/monitor/attack-ranking/stock?limit=5

# 检查债券排行
curl http://localhost:5000/api/monitor/attack-ranking/bond?limit=5
```

---

## 重启服务

### 优雅重启

```powershell
# 1. 查找进程 ID
$process = Get-Process python* | Where-Object { $_.CommandLine -like "*app.py*" }

# 2. 优雅停止
Stop-Process -Id $process.Id -Force

# 3. 等待进程结束
Start-Sleep -Seconds 2

# 4. 重新启动
.\.venv\Scripts\python.exe src\gs2026\dashboard2\app.py
```

### 强制重启脚本

```powershell
# restart_flask.ps1
Write-Host "正在停止 Flask 服务..."
Get-Process python* | Where-Object { 
    $_.CommandLine -like "*dashboard2*" 
} | Stop-Process -Force

Write-Host "清理缓存..."
Remove-Item -Path "src\gs2026\dashboard2\routes\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "启动 Flask 服务..."
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "src\gs2026\dashboard2\app.py" -NoNewWindow

Write-Host "Flask 服务已重启"
```

---

## 常见问题

### 问题1：代码修改未生效

**现象：** 修改代码后，浏览器仍显示旧数据

**原因：** Flask 进程未重启，仍在运行旧代码

**解决：**
```powershell
# 停止所有 Python 进程
Get-Process python* | Stop-Process -Force

# 清理缓存
Remove-Item -Path "src\gs2026\dashboard2\routes\__pycache__" -Recurse -Force

# 重新启动
.\.venv\Scripts\python.exe src\gs2026\dashboard2\app.py
```

---

### 问题2：端口被占用

**现象：** `Address already in use`

**解决：**
```powershell
# 查找占用 5000 端口的进程
netstat -ano | findstr :5000

# 强制结束进程
Stop-Process -Id <PID> -Force
```

---

### 问题3：Redis 连接失败

**现象：** API 返回 500 错误，日志显示 Redis 连接失败

**检查：**
```powershell
# 检查 Redis 服务
redis-cli ping

# 检查 Redis 配置
python -c "from gs2026.utils import config_util; print(config_util.get_config('common.redis'))"
```

---

### 问题4：MySQL 连接失败

**现象：** 降级查询时失败

**检查：**
```powershell
# 检查 MySQL 连接
python -c "
from gs2026.utils import mysql_util
mysql = mysql_util.MysqlTool()
print(mysql.test_connection())
"
```

---

## 监控指标

| 指标 | 检查命令 | 正常值 |
|------|----------|--------|
| 服务状态 | `curl /api/health` | `{"status": "ok"}` |
| 响应时间 | `curl -w "%{time_total}" /api/monitor/attack-ranking/stock?limit=5` | < 500ms |
| Redis 延迟 | `redis-cli --latency` | < 1ms |
| 内存使用 | `Get-Process python* | Select-Object WorkingSet` | < 500MB |

---

## 日志查看

```powershell
# 实时查看日志
tail -f logs\flask.log

# 查看错误日志
Select-String -Path "logs\flask.log" -Pattern "ERROR|Exception" | Select-Object -Last 20

# 查看特定接口日志
Select-String -Path "logs\flask.log" -Pattern "get_bond_ranking|get_stock_ranking" | Select-Object -Last 20
```

---

## 备份与恢复

### 配置备份

```powershell
# 备份配置文件
Copy-Item "src\gs2026\dashboard2\config.py" "backup\config.py.$(Get-Date -Format 'yyyyMMdd')"
```

### 数据备份

```bash
# 备份 Redis 数据
redis-cli BGSAVE
Copy-Item "C:\ProgramData\Redis\dump.rdb" "backup\redis.$(Get-Date -Format 'yyyyMMdd').rdb"

# 备份 MySQL 数据
mysqldump -h 192.168.0.101 -u root -p123456 gs > "backup\gs.$(Get-Date -Format 'yyyyMMdd').sql"
```
