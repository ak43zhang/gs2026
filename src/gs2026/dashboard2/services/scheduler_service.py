"""
Dashboard2 调度中心服务
基于 APScheduler 的定时任务调度服务
"""

import json
import uuid
import importlib
import subprocess
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

import mysql.connector
from gs2026.utils import mysql_util, log_util

logger = log_util.setup_logger(__name__)


def get_db_connection():
    """获取数据库连接"""
    return mysql.connector.connect(
        host=mysql_util.mysql_host,
        port=mysql_util.mysql_port,
        user=mysql_util.mysql_user,
        password=mysql_util.mysql_password,
        database=mysql_util.mysql_database,
        charset="utf8mb4"
    )


def execute_query(sql, params=None):
    """执行查询"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params or ())
        results = cursor.fetchall()
        return results
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def execute_update(sql, params=None):
    """执行更新"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params or ())
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


class SchedulerService:
    """调度服务（单例模式）"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if SchedulerService._initialized:
            return
        
        self.scheduler = BackgroundScheduler(
            timezone='Asia/Shanghai',
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
        
        self._running_executions = {}  # 正在执行的作业
        SchedulerService._initialized = True
        logger.info("SchedulerService initialized")
    
    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")
            # 从数据库加载所有启用的任务
            self._load_jobs_from_db()
    
    def shutdown(self):
        """关闭调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler shutdown")
    
    def is_running(self) -> bool:
        """检查调度器是否运行中"""
        return self.scheduler.running
    
    def _load_jobs_from_db(self):
        """从数据库加载任务"""
        try:
            sql = "SELECT * FROM scheduler_jobs WHERE status = 'enabled'"
            jobs = execute_query(sql)
            
            for job in jobs:
                self._add_job_to_scheduler(job)
            
            logger.info(f"Loaded {len(jobs)} jobs from database")
        except Exception as e:
            logger.error(f"Failed to load jobs from DB: {e}")
    
    def _add_job_to_scheduler(self, job: Dict):
        """添加任务到APScheduler"""
        try:
            trigger_config = json.loads(job['trigger_config']) if isinstance(job['trigger_config'], str) else job['trigger_config']
            trigger = self._create_trigger(job['trigger_type'], trigger_config)
            
            self.scheduler.add_job(
                func=self._execute_job_wrapper,
                trigger=trigger,
                id=job['job_id'],
                args=[job['job_id']],
                replace_existing=True
            )
            
            logger.info(f"Job added to scheduler: {job['job_id']}")
            
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
        elif trigger_type == 'once':
            return DateTrigger(run_date=datetime.now() + timedelta(seconds=5))
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
    
    def _execute_job_wrapper(self, job_id: str):
        """任务执行包装器（供APScheduler调用）"""
        self._execute_job(job_id, trigger_type='scheduled')
    
    def _execute_job(self, job_id: str, trigger_type: str = 'manual', parent_execution_id: Optional[str] = None):
        """执行任务"""
        # 获取任务配置
        sql = "SELECT * FROM scheduler_jobs WHERE job_id = %s"
        job = execute_query(sql, (job_id,))
        job = job[0] if job else None
        
        if not job:
            logger.error(f"Job not found: {job_id}")
            return
        
        # 创建执行记录
        execution_id = self._create_execution(job_id, trigger_type, parent_execution_id)
        start_time = datetime.now()
        
        try:
            # 更新任务状态为运行中
            self._update_job_status(job_id, 'running')
            self._running_executions[execution_id] = {'job_id': job_id, 'start_time': start_time}
            
            # 根据任务类型执行
            job_type = job['job_type']
            job_config = json.loads(job['job_config']) if isinstance(job['job_config'], str) else job['job_config']
            
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
            self._update_job_stats(job_id, 'success', result)
            
            # 触发子任务（链式）
            self._trigger_next_jobs(job, execution_id)
            
        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Job execution failed: {job_id}")
            self._finish_execution(execution_id, 'failed', error_msg, str(e))
            self._update_job_stats(job_id, 'failed', error_msg)
        finally:
            self._update_job_status(job_id, 'enabled')
            if execution_id in self._running_executions:
                del self._running_executions[execution_id]
    
    def _execute_redis_cache_job(self, config: Dict, execution_id: str) -> str:
        """执行Redis缓存任务"""
        module_path = config.get('module')
        function_name = config.get('function')
        params = config.get('params', {})

        # 处理日期参数转换
        # 配置中使用 'date'，但函数参数可能是 'date_str'
        if 'date' in params:
            date_value = params.pop('date')  # 移除 'date'
            if date_value is None:
                date_value = datetime.now().strftime('%Y-%m-%d')
            # 尝试两种参数名
            func_params = {'date_str': date_value}
        else:
            func_params = {}

        # 动态导入模块
        module = importlib.import_module(module_path)
        func = getattr(module, function_name)

        # 检查函数签名，确定正确的参数名
        import inspect
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        # 如果函数接受 'date' 参数，使用 'date'
        # 如果函数接受 'date_str' 参数，使用 'date_str'
        if 'date' in param_names and 'date_str' not in param_names:
            # 函数使用 'date' 参数
            if 'date_str' in func_params:
                func_params['date'] = func_params.pop('date_str')
        elif 'date_str' in param_names:
            # 函数使用 'date_str' 参数，保持原样
            pass

        # 执行函数
        result = func(**func_params)

        return f"Redis cache updated: {result}"
    
    def _execute_dashboard_task(self, config: Dict, execution_id: str) -> str:
        """执行Dashboard2任务"""
        import requests
        
        task_category = config.get('task_category')
        task_id = config.get('task_id')
        params = config.get('params', {})
        
        # 处理日期参数
        if params.get('date') is None:
            params['date'] = datetime.now().strftime('%Y-%m-%d')
        
        # 构建API端点
        base_url = "http://localhost:8080"
        if task_category == 'collection':
            url = f"{base_url}/api/collection/start/{task_id}"
        elif task_category == 'analysis':
            url = f"{base_url}/api/analysis/deepseek/start/{task_id}"
        else:
            raise ValueError(f"Unknown task category: {task_category}")
        
        # 调用API
        response = requests.post(url, json=params, timeout=300)
        response.raise_for_status()
        
        return f"Dashboard task started: {task_id}, response: {response.text}"
    
    def _execute_python_script(self, config: Dict, execution_id: str) -> str:
        """执行Python脚本"""
        script_path = config.get('script_path')
        function_name = config.get('function', 'main')
        params = config.get('params', {})
        working_dir = config.get('working_dir', 'F:/pyworkspace2026/gs2026')
        timeout = config.get('timeout', 3600)
        
        # 处理日期参数
        if params.get('base_date') is None:
            params['base_date'] = datetime.now().strftime('%Y-%m-%d')
        
        # 构建Python命令
        params_str = json.dumps(params)
        python_code = f"""
import sys
sys.path.insert(0, '{working_dir}')
from {script_path} import {function_name}
result = {function_name}(**{params_str})
print(f"Script executed successfully: {{result}}")
"""
        
        # 执行脚本
        result = subprocess.run(
            [sys.executable, '-c', python_code],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Script failed: {result.stderr}")
        
        return f"Script executed: {script_path}.{function_name}\\nOutput: {result.stdout}"
    
    def _execute_chain_job(self, config: Dict, parent_execution_id: str) -> str:
        """执行调度链"""
        steps = config.get('steps', [])
        results = []
        
        for step in steps:
            job_id = step.get('job_id')
            wait = step.get('wait', True)
            
            # 执行子任务
            self._execute_job(job_id, trigger_type='chain', parent_execution_id=parent_execution_id)
            results.append(f"Executed: {job_id}")
        
        return f"Chain executed: {len(steps)} steps\\n" + "\\n".join(results)
    
    def _trigger_next_jobs(self, job: Dict, parent_execution_id: str):
        """触发子任务（链式）"""
        next_job_ids = json.loads(job.get('next_job_ids') or '[]') if isinstance(job.get('next_job_ids'), str) else job.get('next_job_ids', [])
        chain_condition = job.get('chain_condition', 'on_success')
        
        if not next_job_ids:
            return
        
        # 获取父执行状态
        sql = "SELECT status FROM scheduler_execution_log WHERE execution_id = %s"
        result = execute_query(sql, (parent_execution_id,))
        parent_status = result[0]['status'] if result else 'failed'
        
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
                # 延迟执行子任务（避免阻塞）
                self.scheduler.add_job(
                    func=self._execute_job,
                    trigger='date',
                    run_date=datetime.now() + timedelta(seconds=2),
                    args=[next_job_id, 'chain', parent_execution_id],
                    id=f"{next_job_id}_chain_{datetime.now().strftime('%H%M%S')}",
                    replace_existing=True
                )
                logger.info(f"Triggered chain job: {next_job_id} from {job['job_id']}")
    
    def _create_execution(self, job_id: str, trigger_type: str, parent_execution_id: Optional[str] = None) -> str:
        """创建执行记录"""
        execution_id = f"{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        sql = """
            INSERT INTO scheduler_execution_log 
            (job_id, execution_id, trigger_type, parent_execution_id, start_time, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        execute_update(sql, (job_id, execution_id, trigger_type, parent_execution_id, datetime.now(), 'running'))
        
        return execution_id
    
    def _finish_execution(self, execution_id: str, status: str, message: str, error_stack: Optional[str] = None):
        """完成执行记录"""
        end_time = datetime.now()
        
        # 计算执行时长
        sql = "SELECT start_time FROM scheduler_execution_log WHERE execution_id = %s"
        result = execute_query(sql, (execution_id,))
        duration = None
        if result and result[0]['start_time']:
            duration = int((end_time - result[0]['start_time']).total_seconds())
        
        sql = """
            UPDATE scheduler_execution_log 
            SET end_time = %s, status = %s, result_message = %s, error_stack = %s, duration_seconds = %s
            WHERE execution_id = %s
        """
        execute_update(sql, (end_time, status, message, error_stack, duration, execution_id))
    
    def _update_job_status(self, job_id: str, status: str):
        """更新任务状态"""
        sql = "UPDATE scheduler_jobs SET status = %s WHERE job_id = %s"
        execute_update(sql, (status, job_id))
    
    def _update_job_stats(self, job_id: str, run_status: str, message: str):
        """更新任务执行统计"""
        if run_status == 'success':
            sql = """
                UPDATE scheduler_jobs 
                SET last_run_time = %s, last_run_status = %s, last_run_message = %s, run_count = run_count + 1
                WHERE job_id = %s
            """
        else:
            sql = """
                UPDATE scheduler_jobs 
                SET last_run_time = %s, last_run_status = %s, last_run_message = %s, run_count = run_count + 1, fail_count = fail_count + 1
                WHERE job_id = %s
            """
        execute_update(sql, (datetime.now(), run_status, message, job_id))
    
    def _on_job_executed(self, event):
        """任务执行事件监听"""
        if event.exception:
            logger.error(f"Job crashed: {event.job_id}, exception: {event.exception}")
        else:
            logger.info(f"Job executed: {event.job_id}")
    
    # ========== 公共API ==========
    
    def add_job(self, job_config: Dict) -> str:
        """添加任务"""
        job_id = job_config.get('job_id')
        
        # 保存到数据库
        sql = """
            INSERT INTO scheduler_jobs 
            (job_id, job_name, job_type, job_config, trigger_type, trigger_config, 
             parent_job_id, next_job_ids, chain_condition, description, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            job_name = VALUES(job_name),
            job_config = VALUES(job_config),
            trigger_type = VALUES(trigger_type),
            trigger_config = VALUES(trigger_config),
            description = VALUES(description),
            updated_at = CURRENT_TIMESTAMP
        """
        execute_update(sql, (
            job_id,
            job_config.get('job_name'),
            job_config.get('job_type'),
            json.dumps(job_config.get('job_config')),
            job_config.get('trigger_type'),
            json.dumps(job_config.get('trigger_config')),
            job_config.get('parent_job_id'),
            json.dumps(job_config.get('next_job_ids', [])),
            job_config.get('chain_condition', 'on_success'),
            job_config.get('description', ''),
            job_config.get('created_by', 'system')
        ))
        
        # 添加到调度器
        if job_config.get('status') == 'enabled':
            sql = "SELECT * FROM scheduler_jobs WHERE job_id = %s"
            job = execute_query(sql, (job_id,))
            if job:
                self._add_job_to_scheduler(job[0])
        
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
        execute_update(sql, (job_id,))
    
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
        
        if fields:
            sql = f"UPDATE scheduler_jobs SET {', '.join(fields)} WHERE job_id = %s"
            values.append(job_id)
            execute_update(sql, tuple(values))
        
        # 重新加载到调度器
        sql = "SELECT * FROM scheduler_jobs WHERE job_id = %s"
        job = execute_query(sql, (job_id,))
        if job:
            try:
                self.scheduler.remove_job(job_id)
            except:
                pass
            if job[0]['status'] == 'enabled':
                self._add_job_to_scheduler(job[0])
    
    def toggle_job(self, job_id: str, enabled: bool):
        """启用/禁用任务"""
        status = 'enabled' if enabled else 'disabled'
        sql = "UPDATE scheduler_jobs SET status = %s WHERE job_id = %s"
        execute_update(sql, (status, job_id))
        
        if enabled:
            sql = "SELECT * FROM scheduler_jobs WHERE job_id = %s"
            job = execute_query(sql, (job_id,))
            if job:
                self._add_job_to_scheduler(job[0])
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
            args=[job_id, 'manual', None],
            id=f"{job_id}_manual_{datetime.now().strftime('%H%M%S')}",
            replace_existing=False
        )
        return f"Job {job_id} triggered"
    
    def get_jobs(self, filters: Optional[Dict] = None) -> List[Dict]:
        """获取任务列表"""
        sql = "SELECT * FROM scheduler_jobs WHERE 1=1"
        params = []
        
        if filters:
            if filters.get('job_type'):
                sql += " AND job_type = %s"
                params.append(filters['job_type'])
            if filters.get('status'):
                sql += " AND status = %s"
                params.append(filters['status'])
        
        sql += " ORDER BY created_at DESC"
        return execute_query(sql, tuple(params) if params else None)
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """获取任务详情"""
        sql = "SELECT * FROM scheduler_jobs WHERE job_id = %s"
        result = execute_query(sql, (job_id,))
        return result[0] if result else None
    
    def get_executions(self, job_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """获取执行记录"""
        if job_id:
            sql = "SELECT * FROM scheduler_execution_log WHERE job_id = %s ORDER BY start_time DESC LIMIT %s"
            return execute_query(sql, (job_id, limit))
        else:
            sql = "SELECT * FROM scheduler_execution_log ORDER BY start_time DESC LIMIT %s"
            return execute_query(sql, (limit,))
    
    def get_execution(self, execution_id: str) -> Optional[Dict]:
        """获取执行详情"""
        sql = "SELECT * FROM scheduler_execution_log WHERE execution_id = %s"
        result = execute_query(sql, (execution_id,))
        return result[0] if result else None
    
    def get_running_executions(self) -> List[Dict]:
        """获取正在执行的作业"""
        sql = "SELECT * FROM scheduler_execution_log WHERE status = 'running' ORDER BY start_time DESC"
        return execute_query(sql)
    
    def get_scheduler_status(self) -> Dict:
        """获取调度器状态"""
        return {
            'running': self.scheduler.running,
            'jobs_count': len(self.scheduler.get_jobs()),
            'running_executions': len(self._running_executions)
        }


# 全局实例
scheduler_service = SchedulerService()
