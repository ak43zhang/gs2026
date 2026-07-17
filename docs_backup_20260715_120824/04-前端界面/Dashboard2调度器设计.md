# Dashboard2 调度中心设计方案

> 版本: v1.0  
> 创建时间: 2026-03-30  
> 设计目标: 支持3种任务类型、调度链、可扩展、简便可靠

---

## 1. 设计概述

### 1.1 核心需求

| 需求 | 说明 |
|------|------|
| 任务类型1 | 定时生成Redis字典（如红名单缓存、股票债券映射缓存） |
| 任务类型2 | 定时执行采集/分析任务（复用Dashboard2现有任务） |
| 任务类型3 | 定时执行Python脚本（如combine_collection.py、combine_ztb_area.py） |
| 调度链 | 任务A完成后自动触发任务B（如采集→分析→缓存更新） |
| 可扩展 | 后续可轻松添加新的任务类型 |
| 管理功能 | 前端支持增删改查调度任务 |

### 1.2 设计原则

1. **简便**: 使用APScheduler作为调度引擎，配置即代码
2. **可扩展**: 任务类型通过插件化注册，新增类型无需修改核心
3. **可靠**: 任务执行有记录、失败有告警、支持重试
4. **调度链**: 通过任务依赖和事件驱动实现链式执行

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (scheduler.html)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 任务列表  │ │ 添加任务  │ │ 调度链   │ │ 执行记录  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP API
┌────────────────────────▼────────────────────────────────────┐
│                    Flask Backend                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ scheduler.py │ │ scheduler_   │ │ scheduler_   │        │
│  │   (路由)     │ │ service.py   │ │ models.py    │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  APScheduler 调度引擎                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ 定时触发器   │ │ 任务执行器   │ │ 事件监听器   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    任务执行层                                │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ Redis缓存    │ │ Dashboard2   │ │ Python脚本   │        │
│  │ 任务执行器   │ │ 任务执行器   │ │ 任务执行器   │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 数据库设计

### 3.1 调度任务表: scheduler_jobs

```sql
CREATE TABLE scheduler_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL UNIQUE COMMENT '任务唯一标识',
    job_name VARCHAR(128) NOT NULL COMMENT '任务名称',
    job_type ENUM('redis_cache', 'dashboard_task', 'python_script', 'chain') 
        NOT NULL COMMENT '任务类型',
    
    -- 任务配置（JSON格式，根据类型不同）
    job_config JSON NOT NULL COMMENT '任务配置',
    
    -- 调度配置
    trigger_type ENUM('cron', 'interval', 'date', 'once') 
        NOT NULL DEFAULT 'cron' COMMENT '触发器类型',
    trigger_config JSON NOT NULL COMMENT '触发器配置',
    
    -- 调度链配置
    parent_job_id VARCHAR(64) DEFAULT NULL COMMENT '父任务ID（链式）',
    next_job_ids JSON DEFAULT NULL COMMENT '子任务ID列表（链式）',
    chain_condition ENUM('always', 'on_success', 'on_failure') 
        DEFAULT 'on_success' COMMENT '链式触发条件',
    
    -- 状态
    status ENUM('enabled', 'disabled', 'running', 'error') 
        DEFAULT 'enabled' COMMENT '任务状态',
    
    -- 执行统计
    last_run_time DATETIME COMMENT '上次执行时间',
    last_run_status ENUM('success', 'failed', 'timeout') COMMENT '上次执行状态',
    last_run_message TEXT COMMENT '上次执行消息',
    run_count INT DEFAULT 0 COMMENT '执行次数',
    fail_count INT DEFAULT 0 COMMENT '失败次数',
    
    -- 元数据
    description TEXT COMMENT '任务描述',
    created_by VARCHAR(64) COMMENT '创建人',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_job_type (job_type),
    INDEX idx_status (status),
    INDEX idx_parent_job (parent_job_id),
    INDEX idx_last_run_time (last_run_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='调度任务表';
```

### 3.2 任务执行记录表: scheduler_execution_log

```sql
CREATE TABLE scheduler_execution_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL COMMENT '任务ID',
    execution_id VARCHAR(64) NOT NULL UNIQUE COMMENT '执行实例ID',
    
    -- 执行信息
    trigger_type ENUM('scheduled', 'manual', 'chain') DEFAULT 'scheduled' 
        COMMENT '触发方式',
    parent_execution_id VARCHAR(64) DEFAULT NULL COMMENT '父执行ID（链式）',
    
    -- 时间
    start_time DATETIME NOT NULL COMMENT '开始时间',
    end_time DATETIME COMMENT '结束时间',
    duration_seconds INT COMMENT '执行时长',
    
    -- 状态
    status ENUM('pending', 'running', 'success', 'failed', 'timeout', 'skipped') 
        DEFAULT 'pending' COMMENT '执行状态',
    
    -- 结果
    result_message TEXT COMMENT '结果消息',
    error_type VARCHAR(64) COMMENT '错误类型',
    error_stack TEXT COMMENT '错误堆栈',
    output_log TEXT COMMENT '执行输出日志',
    
    -- 链式执行
    next_executions JSON COMMENT '子任务执行ID列表',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_job_id (job_id),
    INDEX idx_status (status),
    INDEX idx_start_time (start_time),
    INDEX idx_parent_execution (parent_execution_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='调度执行记录表';
```

---

## 4. 任务类型设计

### 4.1 类型1: Redis缓存任务

**用途**: 定时生成Redis字典（如红名单缓存、股票债券映射缓存）

**配置示例**:
```json
{
    "cache_type": "red_list",
    "function": "update_red_list_cache",
    "module": "gs2026.dashboard2.routes.red_list_cache",
    "params": {
        "date": null
    }
}
```

**支持的缓存类型**:
| cache_type | 说明 | 函数 |
|------------|------|------|
| red_list | 红名单缓存 | update_red_list_cache |
| stock_bond_mapping | 股票债券映射 | update_mapping_cache |
| industry_mapping | 行业映射 | update_industry_cache |

---

### 4.2 类型2: Dashboard2任务

**用途**: 定时执行采集/分析任务（复用Dashboard2现有任务）

**配置示例**:
```json
{
    "task_category": "collection",
    "task_id": "ztb",
    "params": {
        "date": null
    }
}
```

**task_category**:
| 类别 | 说明 | API端点 |
|------|------|---------|
| collection | 采集任务 | /api/collection/start/{task_id} |
| analysis | 分析任务 | /api/analysis/deepseek/start/{task_id} |

---

### 4.3 类型3: Python脚本任务

**用途**: 定时执行Python脚本（如combine_collection.py）

**配置示例**:
```json
{
    "script_path": "gs2026.analysis.worker.message.deepseek.combine_collection",
    "function": "main",
    "params": {
        "base_date": null
    },
    "working_dir": "F:/pyworkspace2026/gs2026",
    "timeout": 3600
}
```

---

### 4.4 类型4: 调度链任务

**用途**: 将多个任务组合成链式执行

**配置示例**:
```json
{
    "chain_name": "每日完整流程",
    "steps": [
        {"job_id": "collect_ztb", "wait": true},
        {"job_id": "analyze_ztb", "wait": true},
        {"job_id": "update_red_list", "wait": true}
    ]
}
```

---

## 5. 触发器配置

### 5.1 Cron触发器（最常用）

```json
{
    "type": "cron",
    "config": {
        "year": "*",
        "month": "*",
        "day": "*",
        "week": "*",
        "day_of_week": "mon-fri",
        "hour": "9",
        "minute": "30",
        "second": "0"
    }
}
```

**常用表达式**:
| 场景 | Cron配置 |
|------|----------|
| 每日9:30 | `0 30 9 * * *` |
| 每日15:00 | `0 0 15 * * *` |
| 工作日每小时 | `0 0 * * * mon-fri` |
| 每5分钟 | `0 */5 * * * *` |

### 5.2 Interval触发器

```json
{
    "type": "interval",
    "config": {
        "weeks": 0,
        "days": 0,
        "hours": 1,
        "minutes": 0,
        "seconds": 0
    }
}
```

### 5.3 Date触发器（一次性）

```json
{
    "type": "date",
    "config": {
        "run_date": "2026-04-01 09:30:00"
    }
}
```

---

## 6. 调度链实现

### 6.1 链式触发机制

```
任务A (采集) 
    ↓ on_success
任务B (分析)
    ↓ on_success  
任务C (缓存更新)
```

### 6.2 实现方式

**方式1: 配置依赖关系**（推荐）
```json
{
    "job_id": "task_a",
    "next_job_ids": ["task_b"],
    "chain_condition": "on_success"
}
{
    "job_id": "task_b", 
    "next_job_ids": ["task_c"],
    "chain_condition": "on_success"
}
```

**方式2: 链式任务**
```json
{
    "job_id": "daily_pipeline",
    "job_type": "chain",
    "job_config": {
        "steps": ["task_a", "task_b", "task_c"]
    }
}
```

---

## 7. API设计

### 7.1 任务管理API

```python
# scheduler.py

@scheduler_bp.route('/jobs', methods=['GET'])
def list_jobs():
    """获取调度任务列表"""
    pass

@scheduler_bp.route('/jobs', methods=['POST'])
def create_job():
    """创建调度任务"""
    pass

@scheduler_bp.route('/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """获取任务详情"""
    pass

@scheduler_bp.route('/jobs/<job_id>', methods=['PUT'])
def update_job(job_id):
    """更新调度任务"""
    pass

@scheduler_bp.route('/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    """删除调度任务"""
    pass

@scheduler_bp.route('/jobs/<job_id>/toggle', methods=['POST'])
def toggle_job(job_id):
    """启用/禁用任务"""
    pass

@scheduler_bp.route('/jobs/<job_id>/run', methods=['POST'])
def run_job_now(job_id):
    """立即执行任务"""
    pass
```

### 7.2 执行记录API

```python
@scheduler_bp.route('/executions', methods=['GET'])
def list_executions():
    """获取执行记录列表"""
    pass

@scheduler_bp.route('/executions/<execution_id>', methods=['GET'])
def get_execution_detail(execution_id):
    """获取执行详情"""
    pass

@scheduler_bp.route('/executions/<execution_id>/stop', methods=['POST'])
def stop_execution(execution_id):
    """停止正在执行的作业"""
    pass
```

### 7.3 调度链API

```python
@scheduler_bp.route('/chains', methods=['GET'])
def list_chains():
    """获取调度链列表"""
    pass

@scheduler_bp.route('/chains', methods=['POST'])
def create_chain():
    """创建调度链"""
    pass

@scheduler_bp.route('/chains/<chain_id>/run', methods=['POST'])
def run_chain(chain_id):
    """执行调度链"""
    pass
```

---

## 8. 核心代码设计

### 8.1 调度服务类

```python
# scheduler_service.py

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import json
import importlib
from datetime import datetime
from typing import Dict, Any, Optional, List

from gs2026.utils import mysql_util, log_util

logger = log_util.setup_logger(__name__)


class SchedulerService:
    """调度服务（单例）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.scheduler = BackgroundScheduler(
            timezone='Asia/Shanghai',
            jobstores={
                'default': SQLAlchemyJobStore(url=config_util.get_config("common.url"))
            },
            executors={
                'default': ThreadPoolExecutor(max_workers=10)
            },
            job_defaults={
                'coalesce': True,  # 错过的任务合并执行
                'max_instances': 1,  # 同一任务同时只能有一个实例
                'misfire_grace_time': 3600  # 错过1小时内可补执行
            }
        )
        
        # 注册事件监听
        self.scheduler.add_listener(
            self._on_job_executed, 
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )
        
        self.mysql_tool = mysql_util.MysqlTool()
        self._initialized = True
        
    def start(self):
        """启动调度器"""
        self.scheduler.start()
        logger.info("Scheduler started")
        
        # 从数据库加载所有启用的任务
        self._load_jobs_from_db()
    
    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("Scheduler shutdown")
    
    def _load_jobs_from_db(self):
        """从数据库加载任务"""
        sql = "SELECT * FROM scheduler_jobs WHERE status = 'enabled'"
        jobs = self.mysql_tool.query(sql)
        
        for job in jobs:
            self._add_job_to_scheduler(job)
    
    def _add_job_to_scheduler(self, job: Dict):
        """添加任务到APScheduler"""
        try:
            trigger = self._create_trigger(job['trigger_type'], job['trigger_config'])
            
            self.scheduler.add_job(
                func=self._execute_job,
                trigger=trigger,
                id=job['job_id'],
                args=[job['job_id']],
                replace_existing=True
            )
            
            logger.info(f"Job added: {job['job_id']}")
            
        except Exception as e:
            logger.error(f"Failed to add job {job['job_id']}: {e}")
    
    def _create_trigger(self, trigger_type: str, trigger_config: Dict):
        """创建触发器"""
        if trigger_type == 'cron':
            return CronTrigger(**trigger_config)
        elif trigger_type == 'interval':
            return IntervalTrigger(**trigger_config)
        elif trigger_type == 'date':
            return DateTrigger(**trigger_config)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
    
    def _execute_job(self, job_id: str):
        """执行任务"""
        # 获取任务配置
        sql = "SELECT * FROM scheduler_jobs WHERE job_id = %s"
        job = self.mysql_tool.query_one(sql, (job_id,))
        
        if not job:
            logger.error(f"Job not found: {job_id}")
            return
        
        # 创建执行记录
        execution_id = self._create_execution(job_id)
        
        try:
            # 根据任务类型执行
            job_type = job['job_type']
            job_config = json.loads(job['job_config'])
            
            if job_type == 'redis_cache':
                result = self._execute_redis_cache_job(job_config, execution_id)
            elif job_type == 'dashboard_task':
                result = self._execute_dashboard_task(job_config, execution_id)
            elif job_type == 'python_script':
                result = self._execute_python_script(job_config, execution_id)
            elif job_type == 'chain':
                result = self._execute_chain_job(job_config, execution_id)
            else:
                raise ValueError(f"Unknown job type: {job_type}")
            
            # 更新执行成功
            self._finish_execution(execution_id, 'success', result)
            
            # 触发子任务（链式）
            self._trigger_next_jobs(job, execution_id)
            
        except Exception as e:
            logger.error(f"Job execution failed: {job_id}, error: {e}")
            self._finish_execution(execution_id, 'failed', str(e))
    
    def _execute_redis_cache_job(self, config: Dict, execution_id: str) -> str:
        """执行Redis缓存任务"""
        module_path = config['module']
        function_name = config['function']
        params = config.get('params', {})
        
        # 动态导入模块
        module = importlib.import_module(module_path)
        func = getattr(module, function_name)
        
        # 执行函数
        result = func(**params)
        
        return f"Redis cache updated: {result}"
    
    def _execute_dashboard_task(self, config: Dict, execution_id: str) -> str:
        """执行Dashboard2任务"""
        import requests
        
        task_category = config['task_category']
        task_id = config['task_id']
        params = config.get('params', {})
        
        # 构建API端点
        if task_category == 'collection':
            url = f"http://localhost:8080/api/collection/start/{task_id}"
        elif task_category == 'analysis':
            url = f"http://localhost:8080/api/analysis/deepseek/start/{task_id}"
        else:
            raise ValueError(f"Unknown task category: {task_category}")
        
        # 调用API
        response = requests.post(url, json=params)
        response.raise_for_status()
        
        return f"Dashboard task started: {task_id}"
    
    def _execute_python_script(self, config: Dict, execution_id: str) -> str:
        """执行Python脚本"""
        import subprocess
        import os
        
        script_path = config['script_path']
        function_name = config.get('function', 'main')
        params = config.get('params', {})
        working_dir = config.get('working_dir', 'F:/pyworkspace2026/gs2026')
        timeout = config.get('timeout', 3600)
        
        # 构建命令
        params_str = json.dumps(params)
        cmd = [
            'python', '-c',
            f"import sys; sys.path.insert(0, '{working_dir}'); "
            f"from {script_path} import {function_name}; "
            f"{function_name}(**{params_str})"
        ]
        
        # 执行脚本
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Script failed: {result.stderr}")
        
        return f"Script executed: {script_path}.{function_name}"
    
    def _execute_chain_job(self, config: Dict, execution_id: str) -> str:
        """执行调度链"""
        steps = config.get('steps', [])
        
        for step in steps:
            job_id = step['job_id']
            wait = step.get('wait', True)
            
            # 执行子任务
            self._execute_job(job_id)
            
            # 如果需要等待，检查执行结果
            if wait:
                # 等待执行完成（通过轮询或事件）
                pass
        
        return f"Chain executed: {len(steps)} steps"
    
    def _trigger_next_jobs(self, job: Dict, parent_execution_id: str):
        """触发子任务（链式）"""
        next_job_ids = json.loads(job.get('next_job_ids') or '[]')
        chain_condition = job.get('chain_condition', 'on_success')
        
        # 获取父执行状态
        sql = "SELECT status FROM scheduler_execution_log WHERE execution_id = %s"
        result = self.mysql_tool.query_one(sql, (parent_execution_id,))
        parent_status = result['status'] if result else 'failed'
        
        # 检查触发条件
        should_trigger = False
        if chain_condition == 'always':
            should_trigger = True
        elif chain_condition == 'on_success' and parent_status == 'success':
            should_trigger = True
        elif chain_condition == 'on_failure' and parent_status == 'failed':
            should_trigger = True
        
        if should_trigger:
            for next_job_id in next_job_ids:
                # 立即触发子任务
                self._execute_job(next_job_id)
    
    def _create_execution(self, job_id: str) -> str:
        """创建执行记录"""
        execution_id = f"{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        sql = """
            INSERT INTO scheduler_execution_log 
            (job_id, execution_id, start_time, status)
            VALUES (%s, %s, %s, %s)
        """
        self.mysql_tool.execute(sql, (job_id, execution_id, datetime.now(), 'running'))
        
        return execution_id
    
    def _finish_execution(self, execution_id: str, status: str, message: str):
        """完成执行记录"""
        sql = """
            UPDATE scheduler_execution_log 
            SET end_time = %s, status = %s, result_message = %s
            WHERE execution_id = %s
        """
        self.mysql_tool.execute(sql, (datetime.now(), status, message, execution_id))
    
    def _on_job_executed(self, event):
        """任务执行事件监听"""
        if event.exception:
            logger.error(f"Job crashed: {event.job_id}, exception: {event.exception}")
        else:
            logger.info(f"Job executed: {event.job_id}")
    
    # ========== 公共API ==========
    
    def add_job(self, job_config: Dict) -> str:
        """添加任务"""
        job_id = job_config['job_id']
        
        # 保存到数据库
        sql = """
            INSERT INTO scheduler_jobs 
            (job_id, job_name, job_type, job_config, trigger_type, trigger_config, 
             description, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        self.mysql_tool.execute(sql, (
            job_id,
            job_config['job_name'],
            job_config['job_type'],
            json.dumps(job_config['job_config']),
            job_config['trigger_type'],
            json.dumps(job_config['trigger_config']),
            job_config.get('description', ''),
            job_config.get('created_by', 'system')
        ))
        
        # 添加到调度器
        if job_config.get('status') == 'enabled':
            self._add_job_to_scheduler(job_config)
        
        return job_id
    
    def remove_job(self, job_id: str):
        """删除任务"""
        # 从调度器移除
        try:
            self.scheduler.remove_job(job_id)
        except:
            pass
        
        # 从数据库删除
        sql = "DELETE FROM scheduler_jobs WHERE job_id = %s"
        self.mysql_tool.execute(sql, (job_id,))
    
    def update_job(self, job_id: str, updates: Dict):
        """更新任务"""
        # 更新数据库
        fields = []
        values = []
        for key, value in updates.items():
            if key in ['job_config', 'trigger_config', 'next_job_ids']:
                value = json.dumps(value)
            fields.append(f"{key} = %s")
            values.append(value)
        
        sql = f"UPDATE scheduler_jobs SET {', '.join(fields)} WHERE job_id = %s"
        values.append(job_id)
        self.mysql_tool.execute(sql, tuple(values))
        
        # 重新加载到调度器
        sql = "SELECT * FROM scheduler_jobs WHERE job_id = %s"
        job = self.mysql_tool.query_one(sql, (job_id,))
        if job:
            self.scheduler.remove_job(job_id)
            if job['status'] == 'enabled':
                self._add_job_to_scheduler(job)
    
    def toggle_job(self, job_id: str, enabled: bool):
        """启用/禁用任务"""
        status = 'enabled' if enabled else 'disabled'
        sql = "UPDATE scheduler_jobs SET status = %s WHERE job_id = %s"
        self.mysql_tool.execute(sql, (status, job_id))
        
        if enabled:
            sql = "SELECT * FROM scheduler_jobs WHERE job_id = %s"
            job = self.mysql_tool.query_one(sql, (job_id,))
            if job:
                self._add_job_to_scheduler(job)
        else:
            try:
                self.scheduler.remove_job(job_id)
            except:
                pass
    
    def run_job_now(self, job_id: str) -> str:
        """立即执行任务"""
        # 使用scheduler的add_job立即执行
        self.scheduler.add_job(
            func=self._execute_job,
            trigger='date',
            run_date=datetime.now(),
            args=[job_id],
            id=f"{job_id}_manual_{datetime.now().strftime('%H%M%S')}"
        )
        return f"Job {job_id} triggered"


# 全局实例
scheduler_service = SchedulerService()
```

---

## 9. 前端设计

### 9.1 页面结构

```
┌─────────────────────────────────────────────────────────────┐
│  GS2026 - 调度中心                    [首页] [监控] [调度]  │
├─────────────────────────────────────────────────────────────┤
│  [➕ 新建任务] [▶ 启动调度器] [⏹ 停止调度器]              │
├─────────────────────────────────────────────────────────────┤
│  📋 任务列表                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ [复选框] 任务名称    类型      调度        状态  操作 │   │
│  │ [✓] 每日红名单更新  Redis缓存  09:30每天  启用  [编辑] │   │
│  │ [✓] 涨停板数据采集  采集任务   09:35每天  启用  [编辑] │   │
│  │ [ ] 收盘分析脚本    Python脚本 15:05每天  禁用  [编辑] │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  🔗 调度链                                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 每日完整流程: 采集 → 分析 → 缓存更新                 │   │
│  │ [立即执行] [编辑链]                                  │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  📊 执行记录                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 时间        任务        状态    耗时   操作          │   │
│  │ 09:30:05   红名单更新   成功    2.3s  [详情]         │   │
│  │ 09:35:12   涨停板采集   失败    5.1s  [详情] [重试]  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 新建任务弹窗

```
┌────────────────────────────────────────┐
│  ➕ 新建调度任务                        │
├────────────────────────────────────────┤
│  任务名称: [________________]          │
│  任务类型: [Redis缓存 ▼]               │
│                                        │
│  ── Redis缓存配置 ──                   │
│  缓存类型: [红名单 ▼]                  │
│  函数: update_red_list_cache           │
│  模块: gs2026...red_list_cache         │
│                                        │
│  ── 调度配置 ──                        │
│  触发器: [Cron ▼]                      │
│  Cron: 0 30 9 * * *                    │
│  (每天 09:30:00)                       │
│                                        │
│  ── 调度链 ──                          │
│  执行后触发: [选择后续任务...]          │
│  触发条件: [成功后 ▼]                  │
│                                        │
│  [取消]              [创建]            │
└────────────────────────────────────────┘
```

---

## 10. 实施计划

### 阶段一：基础框架（2天）
- [ ] 创建数据库表
- [ ] 实现 SchedulerService 核心类
- [ ] 实现3种任务类型的执行器
- [ ] 添加 Flask 路由

### 阶段二：调度链（1天）
- [ ] 实现任务依赖关系
- [ ] 实现链式触发机制
- [ ] 测试调度链执行

### 阶段三：前端（1.5天）
- [ ] 完善 scheduler.html
- [ ] 实现任务列表、添加、编辑
- [ ] 实现调度链可视化
- [ ] 实现执行记录展示

### 阶段四：集成测试（0.5天）
- [ ] 集成测试
- [ ] 性能优化
- [ ] 文档完善

---

## 11. 文件清单

| 文件 | 说明 |
|------|------|
| `gs2026/dashboard2/routes/scheduler.py` | API路由 |
| `gs2026/dashboard2/services/scheduler_service.py` | 调度服务 |
| `gs2026/dashboard2/models/scheduler_models.py` | 数据模型 |
| `gs2026/dashboard2/templates/scheduler.html` | 前端页面 |
| `gs2026/dashboard2/static/js/scheduler.js` | 前端JS |

---

## 12. 依赖安装

```bash
pip install apscheduler
```

---

**设计方案完成，等待确认后实施。**
