"""
进程监控管理工具 - Redis-based Process Monitor

功能：
1. 进程注册/注销
2. 心跳检测
3. 自动状态更新
4. 进程保活/自动重启（可选）

使用示例：
    from gs2026.utils.process_monitor import ProcessMonitor
    
    monitor = ProcessMonitor()
    
    # 注册进程
    monitor.register('collection', pid=12345, meta={'type': 'data_collection'})
    
    # 检查状态
    status = monitor.get_status('collection')
    
    # 启动监控线程
    monitor.start_monitoring()
    
    # 停止监控
    monitor.stop_monitoring()
"""

import threading
import time
import psutil
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
import json

from gs2026.utils import redis_util

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    """进程信息"""
    process_id: str
    service_id: str
    instance_id: str
    pid: int
    status: str
    start_time: str
    stop_time: Optional[str]
    last_heartbeat: str
    process_type: str
    params: Dict
    meta: Dict
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ProcessInfo':
        # 兼容旧数据格式
        if 'service_id' not in data:
            data['service_id'] = data.get('process_id', '').split('_')[0]
        if 'instance_id' not in data:
            data['instance_id'] = '1'
        if 'stop_time' not in data:
            data['stop_time'] = None
        if 'params' not in data:
            data['params'] = {}
        return cls(**data)


class ProcessMonitor:
    """进程监控管理器"""
    
    KEY_PROCESS = "process:{process_id}"
    KEY_HEARTBEAT = "process:heartbeat:{process_id}"
    KEY_REGISTRY = "process:registry"
    
    DEFAULT_CHECK_INTERVAL = 10
    DEFAULT_HEARTBEAT_TIMEOUT = 30
    
    def __init__(self, check_interval: int = None, heartbeat_timeout: int = None):
        self.check_interval = check_interval or self.DEFAULT_CHECK_INTERVAL
        self.heartbeat_timeout = heartbeat_timeout or self.DEFAULT_HEARTBEAT_TIMEOUT
        
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._callbacks: Dict[str, Callable] = {}
        
        if not redis_util._redis_client:
            redis_util.init_redis()
    
    def _get_redis(self):
        return redis_util._get_redis_client()
    
    def register(self, process_id: str, service_id: str, instance_id: str, pid: int, 
                 process_type: str = "default", params: Dict = None, 
                 meta: Dict = None, auto_restart: bool = False) -> bool:
        """注册进程到监控系统"""
        try:
            now = datetime.now().isoformat()
            info = ProcessInfo(
                process_id=process_id,
                service_id=service_id,
                instance_id=instance_id,
                pid=pid,
                status="running",
                start_time=now,
                stop_time=None,
                last_heartbeat=now,
                process_type=process_type,
                params=params or {},
                meta=meta or {}
            )
            
            redis_key = self.KEY_PROCESS.format(process_id=process_id)
            self._get_redis().set(redis_key, json.dumps(info.to_dict()))
            self._get_redis().sadd(self.KEY_REGISTRY, process_id)
            
            # 添加到服务实例集合
            self._get_redis().sadd(f"process:service:{service_id}", process_id)
            
            if auto_restart:
                self._get_redis().set(f"{redis_key}:auto_restart", "1")
            
            logger.info(f"Process registered: {process_id} (PID: {pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to register process {process_id}: {e}")
            return False
    
    def unregister(self, process_id: str) -> bool:
        """注销进程"""
        try:
            # 获取进程信息以获取 service_id
            info = self.get_status(process_id)
            
            redis_key = self.KEY_PROCESS.format(process_id=process_id)
            self._get_redis().delete(redis_key)
            self._get_redis().delete(f"{redis_key}:auto_restart")
            self._get_redis().srem(self.KEY_REGISTRY, process_id)
            
            # 从服务实例集合移除
            if info:
                self._get_redis().srem(f"process:service:{info.service_id}", process_id)
            
            logger.info(f"Process unregistered: {process_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to unregister process {process_id}: {e}")
            return False
    
    def update_heartbeat(self, process_id: str, status: str = "running", 
                         extra_data: Dict = None) -> bool:
        """更新进程心跳"""
        try:
            now = datetime.now().isoformat()
            heartbeat_key = self.KEY_HEARTBEAT.format(process_id=process_id)
            
            data = {"timestamp": now, "status": status}
            if extra_data:
                data.update(extra_data)
            
            self._get_redis().set(heartbeat_key, json.dumps(data))
            
            redis_key = self.KEY_PROCESS.format(process_id=process_id)
            info_data = self._get_redis().get(redis_key)
            if info_data:
                info = ProcessInfo.from_dict(json.loads(info_data))
                info.last_heartbeat = now
                if status:
                    info.status = status
                self._get_redis().set(redis_key, json.dumps(info.to_dict()))
            
            return True
        except Exception as e:
            logger.error(f"Failed to update heartbeat {process_id}: {e}")
            return False
    
    def get_status(self, process_id: str) -> Optional[ProcessInfo]:
        """获取进程状态（实时检查进程是否存在）"""
        try:
            redis_key = self.KEY_PROCESS.format(process_id=process_id)
            data = self._get_redis().get(redis_key)
            if data:
                info = ProcessInfo.from_dict(json.loads(data))
                
                # 实时检查进程是否存在
                if info.status == 'running' and info.pid:
                    try:
                        process = psutil.Process(info.pid)
                        if not process.is_running():
                            # 进程已退出，更新状态
                            info.status = 'stopped'
                            info.stop_time = datetime.now().isoformat()
                            self._get_redis().set(redis_key, json.dumps(info.to_dict()))
                            logger.info(f"Process {process_id} (PID: {info.pid}) detected as stopped")
                        elif process.name().lower() not in ['python.exe', 'python']:
                            # PID 被其他进程复用（如 Firefox），更新状态
                            logger.warning(f"Process {process_id} PID {info.pid} reused by {process.name()}, marking as stopped")
                            info.status = 'stopped'
                            info.stop_time = datetime.now().isoformat()
                            self._get_redis().set(redis_key, json.dumps(info.to_dict()))
                    except psutil.NoSuchProcess:
                        # 进程不存在，更新状态
                        info.status = 'stopped'
                        info.stop_time = datetime.now().isoformat()
                        self._get_redis().set(redis_key, json.dumps(info.to_dict()))
                        logger.info(f"Process {process_id} (PID: {info.pid}) not found, marked as stopped")
                
                return info
            return None
        except Exception as e:
            logger.error(f"Failed to get status {process_id}: {e}")
            return None
    
    def get_all_processes(self, process_type: str = None, include_stopped: bool = True) -> List[ProcessInfo]:
        """获取所有注册进程
        
        Args:
            process_type: 按类型过滤
            include_stopped: 是否包含已停止的进程
        """
        try:
            process_ids = self._get_redis().smembers(self.KEY_REGISTRY)
            processes = []
            
            for pid_bytes in process_ids:
                process_id = pid_bytes.decode('utf-8') if isinstance(pid_bytes, bytes) else pid_bytes
                info = self.get_status(process_id)
                if info:
                    if process_type is None or info.process_type == process_type:
                        if include_stopped or info.status == 'running':
                            processes.append(info)
            
            # 排序：运行中的在前，停止的按停止时间倒序
            processes.sort(key=lambda x: (
                0 if x.status == 'running' else 1,
                x.stop_time or '9999'  # 停止时间倒序
            ), reverse=False)
            
            return processes
        except Exception as e:
            logger.error(f"Failed to get process list: {e}")
            return []
    
    def get_service_instances(self, service_id: str) -> List[ProcessInfo]:
        """获取指定服务的所有实例"""
        try:
            process_ids = self._get_redis().smembers(f"process:service:{service_id}")
            processes = []
            
            for pid_bytes in process_ids:
                process_id = pid_bytes.decode('utf-8') if isinstance(pid_bytes, bytes) else pid_bytes
                info = self.get_status(process_id)
                if info:
                    processes.append(info)
            
            return processes
        except Exception as e:
            logger.error(f"Failed to get service instances: {e}")
            return []
    
    def get_running_count(self, service_id: str) -> int:
        """获取指定服务的运行中实例数"""
        instances = self.get_service_instances(service_id)
        return sum(1 for p in instances if p.status == 'running')
    
    def is_running(self, process_id: str) -> bool:
        """检查进程是否运行中"""
        info = self.get_status(process_id)
        if not info:
            return False
        
        try:
            proc = psutil.Process(info.pid)
            return proc.is_running()
        except psutil.NoSuchProcess:
            return False
    
    def _check_processes(self):
        """检查所有进程状态"""
        try:
            processes = self.get_all_processes()
            
            for info in processes:
                process_id = info.process_id
                
                is_alive = False
                try:
                    proc = psutil.Process(info.pid)
                    is_alive = proc.is_running()
                except psutil.NoSuchProcess:
                    is_alive = False
                
                if not is_alive:
                    if info.status != "stopped":
                        logger.info(f"Process stopped: {process_id} (PID: {info.pid})")
                        self._update_status(process_id, "stopped")
                        self._trigger_callback(process_id, "stopped", info)
                        
                        redis_key = self.KEY_PROCESS.format(process_id=process_id)
                        auto_restart = self._get_redis().get(f"{redis_key}:auto_restart")
                        if auto_restart and auto_restart.decode('utf-8') == "1":
                            self._trigger_callback(process_id, "auto_restart", info)
                else:
                    if info.status == "stopped":
                        self._update_status(process_id, "running")
                        self._trigger_callback(process_id, "resumed", info)
                    
                    self.update_heartbeat(process_id, "running")
                    
        except Exception as e:
            logger.error(f"Error checking processes: {e}")
    
    def _update_status(self, process_id: str, status: str):
        """更新进程状态"""
        try:
            redis_key = self.KEY_PROCESS.format(process_id=process_id)
            data = self._get_redis().get(redis_key)
            if data:
                info = ProcessInfo.from_dict(json.loads(data))
                info.status = status
                if status == 'stopped':
                    info.stop_time = datetime.now().isoformat()
                self._get_redis().set(redis_key, json.dumps(info.to_dict()))
        except Exception as e:
            logger.error(f"Failed to update status {process_id}: {e}")
    
    def _monitor_loop(self):
        """监控循环"""
        logger.info(f"Monitor thread started, interval: {self.check_interval}s")
        
        while not self._stop_event.is_set():
            self._check_processes()
            self._stop_event.wait(self.check_interval)
        
        logger.info("Monitor thread stopped")
    
    def start_monitoring(self):
        """启动监控线程"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.info("Monitor thread already running")
            return
        
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitoring(self):
        """停止监控线程"""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def on_status_change(self, process_id: str, callback: Callable):
        """注册状态变更回调"""
        self._callbacks[process_id] = callback
    
    def _trigger_callback(self, process_id: str, status: str, info: ProcessInfo):
        """触发回调"""
        if process_id in self._callbacks:
            try:
                self._callbacks[process_id](process_id, status, info)
            except Exception as e:
                logger.error(f"Callback failed {process_id}: {e}")
        
        if "*" in self._callbacks:
            try:
                self._callbacks["*"](process_id, status, info)
            except Exception as e:
                logger.error(f"Global callback failed: {e}")
    
    def cleanup_stopped(self, max_age_days: int = 7) -> int:
        """清理已停止的进程记录
        
        Args:
            max_age_days: 保留天数，默认7天
        """
        try:
            from datetime import timedelta
            
            processes = self.get_all_processes()
            cleaned = 0
            cutoff_time = datetime.now() - timedelta(days=max_age_days)
            
            for info in processes:
                if info.status == "stopped" and info.stop_time:
                    stop_time = datetime.fromisoformat(info.stop_time)
                    if stop_time < cutoff_time:
                        self.unregister(info.process_id)
                        cleaned += 1
            
            return cleaned
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0


_process_monitor_instance: Optional[ProcessMonitor] = None


def get_process_monitor() -> ProcessMonitor:
    """获取全局进程监控器实例"""
    global _process_monitor_instance
    if _process_monitor_instance is None:
        _process_monitor_instance = ProcessMonitor()
    return _process_monitor_instance