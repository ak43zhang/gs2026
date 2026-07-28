# 调度中心现状分析与Windows服务化方案

> **版本**: v1.0  
> **日期**: 2026-07-29  
> **状态**: 待审核  
> **需求**: app.py不启动也能调度，改为Windows服务模式

---

## 一、当前调度中心实现分析

### 1.1 当前架构

```
┌─────────────────────────────────────────┐
│  调度中心组件                            │
├─────────────────────────────────────────┤
│  scheduler.py (路由层)                  │
│  - /api/scheduler/start    手动启动     │
│  - /api/scheduler/stop     手动停止     │
│  - /api/scheduler/jobs     任务CRUD     │
│  - /api/scheduler/executions 执行记录   │
├─────────────────────────────────────────┤
│  scheduler_service.py (服务层)          │
│  - APScheduler BackgroundScheduler      │
│  - 任务存储: MySQL (scheduler_jobs表)   │
│  - 执行记录: MySQL (scheduler_execution_log表)
│  - 调度逻辑: 内存中运行 (app启动后)      │
└─────────────────────────────────────────┘
```

### 1.2 当前调度流程

```
1. 用户访问调度中心页面 (scheduler.html)
2. 用户点击"启动调度器"按钮
3. 调用 POST /api/scheduler/start
4. scheduler_service.start() 启动 APScheduler
5. APScheduler 从 MySQL 加载 enabled 任务
6. 任务在后台线程按触发器执行
7. 执行结果写入 MySQL
```

### 1.3 核心问题

| 问题 | 说明 |
|------|------|
| **依赖app.py** | 调度器是dashboard2的一个Blueprint，必须在Flask app内启动 |
| **手动启动** | 需要用户点击"启动"或调用API，不能自动运行 |
| **进程绑定** | app.py停止 → 调度器停止 → 所有任务中断 |
| **无持久化调度** | 没有独立的Windows服务，不能开机自启 |

### 1.4 代码证据

```python
# scheduler.py 行434 - 需要手动调用API启动
@scheduler_bp.route('/start', methods=['POST'])
def start_scheduler():
    scheduler_service.start()  # 这里才启动

# scheduler_service.py 行92-114
class SchedulerService:
    def __init__(self):
        self.scheduler = BackgroundScheduler(...)  # 创建但不启动
    
    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()  # 手动启动
            self._load_jobs_from_db()  # 从MySQL加载任务
```

---

## 二、用户期望 vs 当前实现

| 期望 | 当前 | 差距 |
|------|------|------|
| **app.py不启动也能调度** | 必须启动app.py | ❌ 不满足 |
| **Windows服务模式** | Flask Blueprint | ❌ 不满足 |
| **开机自启** | 手动启动 | ❌ 不满足 |
| **独立进程** | 与app.py同进程 | ❌ 不满足 |

---

## 三、优化方案：Windows服务化改造

### 3.1 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│  Windows 服务层 (独立)                                       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  GS2026 Scheduler Service (Windows Service)             │ │
│  │  - 独立Python进程                                        │ │
│  │  - 开机自启                                              │ │
│  │  - 无界面运行                                            │ │
│  │  - 与app.py解耦                                          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  APScheduler (独立进程内运行)                              │ │
│  │  - 从MySQL加载任务                                       │ │
│  │  - 按触发器执行                                           │ │
│  │  - 写入执行记录                                           │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Dashboard2 (Flask app.py) - 可选启动                        │
│  - 只读查看任务/执行记录                                       │
│  - 修改任务配置（写入MySQL）                                   │
│  - 触发立即执行（通过某种IPC机制）                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 方案对比

| 方案 | 描述 | 优点 | 缺点 | 推荐 |
|------|------|------|------|------|
| **A. Windows服务** | 用pywin32创建Windows服务 | 标准方案，开机自启，稳定 | Windows专用，需管理员权限 | ✅ **首选** |
| **B. 计划任务** | Windows Task Scheduler | 无需代码改动，配置简单 | 粒度粗，不适合高频任务 | 备选 |
| **C. 独立进程** | pythonw.exe后台运行 | 简单，跨平台 | 无自启，需手动管理 | 不推荐 |
| **D. 系统服务** | 用nssm包装成服务 | 简单，无需改代码 | 依赖外部工具 | 备选 |

---

## 四、推荐方案A：Windows服务化实施

### 4.1 实施步骤

#### 步骤1：创建独立调度服务脚本

**新文件**: `src/gs2026/scheduler_service/scheduler_daemon.py`

```python
"""
GS2026 调度服务 - Windows服务版
独立进程，不依赖app.py
"""

import sys
import os
import time
import servicemanager
import win32serviceutil
import win32service
import win32event

# 添加项目路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gs2026.dashboard2.services.scheduler_service import scheduler_service
from gs2026.utils import log_util

logger = log_util.setup_logger(__name__)


class SchedulerService(win32serviceutil.ServiceFramework):
    """Windows服务包装器"""
    
    _svc_name_ = "GS2026Scheduler"
    _svc_display_name_ = "GS2026 Scheduler Service"
    _svc_description_ = "GS2026 调度中心服务 - 独立于Dashboard运行"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_alive = True
    
    def SvcStop(self):
        """服务停止"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_alive = False
        
        # 停止调度器
        try:
            scheduler_service.shutdown()
            logger.info("Scheduler service stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    def SvcDoRun(self):
        """服务运行"""
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        logger.info("Scheduler service starting...")
        
        try:
            # 启动调度器
            scheduler_service.start()
            logger.info("Scheduler started successfully")
            
            # 保持服务运行
            while self.is_alive:
                # 检查停止事件
                rc = win32event.WaitForSingleObject(self.hWaitStop, 5000)
                if rc == win32event.WAIT_OBJECT_0:
                    break
                    
        except Exception as e:
            logger.error(f"Scheduler service error: {e}")
            raise


def run_as_service():
    """作为Windows服务运行"""
    win32serviceutil.HandleCommandLine(SchedulerService)


def run_as_console():
    """作为控制台应用运行（调试模式）"""
    logger.info("Running in console mode...")
    try:
        scheduler_service.start()
        logger.info("Scheduler started. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping...")
        scheduler_service.shutdown()


if __name__ == '__main__':
    if len(sys.argv) == 1:
        # 无参数：作为控制台运行
        run_as_console()
    else:
        # 有参数：作为服务运行 (install/start/stop/remove)
        run_as_service()
```

#### 步骤2：创建服务安装脚本

**新文件**: `scripts/install_scheduler_service.bat`

```batch
@echo off
chcp 65001 >nul
echo ==========================================
echo GS2026 调度服务安装脚本
echo ==========================================

set PYTHON_PATH=.venv\Scripts\python.exe
if not exist %PYTHON_PATH% (
    echo 错误: 未找到Python环境: %PYTHON_PATH%
    exit /b 1
)

echo [1/4] 检查管理员权限...
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 错误: 需要管理员权限运行此脚本
    echo 请右键以管理员身份运行
    pause
    exit /b 1
)

echo [2/4] 安装服务...
%PYTHON_PATH% src\gs2026\scheduler_service\scheduler_daemon.py install

echo [3/4] 设置开机自启...
sc config GS2026Scheduler start= auto

echo [4/4] 启动服务...
net start GS2026Scheduler

echo ==========================================
echo 服务安装完成!
echo 服务名: GS2026Scheduler
echo 显示名: GS2026 Scheduler Service
echo ==========================================
pause
```

#### 步骤3：修改dashboard2调度路由

**修改**: `src/gs2026/dashboard2/routes/scheduler.py`

```python
# 移除手动start/stop，改为查询服务状态

@scheduler_bp.route('/status', methods=['GET'])
def get_scheduler_status():
    """获取调度器状态（查询Windows服务状态）"""
    try:
        import win32service
        import win32serviceutil
        
        # 查询Windows服务状态
        try:
            status = win32serviceutil.QueryServiceStatus('GS2026Scheduler')
            service_running = (status[1] == win32service.SERVICE_RUNNING)
        except:
            service_running = False
        
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'service_running': service_running,
                'service_name': 'GS2026Scheduler',
                'mode': 'windows_service'
            }
        })
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        return jsonify({'code': 500, 'message': str(e)}), 500


# 移除以下路由（服务由Windows管理）
# @scheduler_bp.route('/start', methods=['POST'])
# @scheduler_bp.route('/stop', methods=['POST'])
```

#### 步骤4：创建服务管理工具

**新文件**: `scripts/manage_scheduler.bat`

```batch
@echo off
chcp 65001 >nul
:menu
cls
echo ==========================================
echo GS2026 调度服务管理工具
echo ==========================================
echo 1. 安装服务
echo 2. 卸载服务
echo 3. 启动服务
echo 4. 停止服务
echo 5. 重启服务
echo 6. 查看状态
echo 7. 以控制台模式运行（调试）
echo 0. 退出
echo ==========================================
set /p choice=请选择: 

if "%choice%"=="1" goto install
if "%choice%"=="2" goto uninstall
if "%choice%"=="3" goto start
if "%choice%"=="4" goto stop
if "%choice%"=="5" goto restart
if "%choice%"=="6" goto status
if "%choice%"=="7" goto console
if "%choice%"=="0" exit

goto menu

:install
call scripts\install_scheduler_service.bat
goto menu

:uninstall
net stop GS2026Scheduler
.venv\Scripts\python.exe src\gs2026\scheduler_service\scheduler_daemon.py remove
echo 服务已卸载
pause
goto menu

:start
net start GS2026Scheduler
echo 服务已启动
pause
goto menu

:stop
net stop GS2026Scheduler
echo 服务已停止
pause
goto menu

:restart
net stop GS2026Scheduler
net start GS2026Scheduler
echo 服务已重启
pause
goto menu

:status
sc query GS2026Scheduler
pause
goto menu

:console
.venv\Scripts\python.exe src\gs2026\scheduler_service\scheduler_daemon.py
goto menu
```

### 4.2 依赖安装

```bash
# 安装Windows服务依赖
pip install pywin32
```

### 4.3 改造后架构

```
┌─────────────────────────────────────────────────────────┐
│  Windows 系统                                             │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  GS2026Scheduler (Windows Service)                  │ │
│  │  - 开机自动启动                                      │ │
│  │  - 独立Python进程                                    │ │
│  │  - 无界面后台运行                                    │ │
│  │  - 与app.py无关                                      │ │
│  └─────────────────────────────────────────────────────┘ │
│                          │                              │
│                          ▼                              │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  APScheduler + MySQL                               │ │
│  │  - 任务配置存储在MySQL                               │ │
│  │  - 执行记录写入MySQL                                 │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼ (读写)
┌─────────────────────────────────────────────────────────┐
│  Dashboard2 (可选启动)                                    │
│  - 查看任务列表 (只读)                                    │
│  - 修改任务配置 (写MySQL)                                 │
│  - 查看执行记录 (只读)                                    │
│  - 触发立即执行 (通过MySQL/API)                           │
└─────────────────────────────────────────────────────────┘
```

---

## 五、实施检查清单

- [ ] 创建 `src/gs2026/scheduler_service/` 目录
- [ ] 创建 `scheduler_daemon.py` Windows服务脚本
- [ ] 创建 `scripts/install_scheduler_service.bat` 安装脚本
- [ ] 创建 `scripts/manage_scheduler.bat` 管理工具
- [ ] 修改 `scheduler.py` 移除start/stop路由，改为查询服务状态
- [ ] 安装依赖 `pip install pywin32`
- [ ] 以管理员身份运行安装脚本
- [ ] 验证服务状态 `sc query GS2026Scheduler`
- [ ] 重启电脑验证开机自启
- [ ] 停止app.py验证调度仍运行
- [ ] 更新调度中心页面（移除启动/停止按钮，改为显示服务状态）

---

## 六、回退方案

```batch
# 卸载服务
net stop GS2026Scheduler
python src/gs2026/scheduler_service/scheduler_daemon.py remove
```

---

**请审核方案，确认后我立即实施。**
