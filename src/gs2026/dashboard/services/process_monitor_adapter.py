"""
ProcessManager 与 ProcessMonitor 的适配器

提供无侵入集成：
1. 保持 ProcessManager 原有接口不变
2. 自动将进程注册到 Redis 监控
3. 自动监听进程状态变化

使用：
    在 ProcessManager 中替换为：
    from gs2026.dashboard.services.process_monitor_adapter import ProcessManagerWithMonitor
    
    class ProcessManager(ProcessManagerWithMonitor):
        # 原有代码无需修改
        pass
"""

import subprocess
import psutil
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from gs2026.utils.process_monitor import ProcessMonitor, get_process_monitor

logger = logging.getLogger(__name__)


class ProcessManagerWithMonitor:
    """
    带监控的进程管理器基类
    
    特性：
    - 完全兼容原有 ProcessManager 接口
    - 自动注册进程到 Redis 监控
    - 自动检测进程停止并更新状态
    - 支持状态变更回调
    """
    
    def __init__(self):
        # 原有属性
        self.processes = {
            'collection': None,
            'analysis': None,
            'monitor': None
        }
        self.services = {}
        self.analysis_services = {}
        
        self.project_root = Path(__file__).parent.parent.parent.parent.parent
        self.python_exe = r"F:\python312\python.exe"
        self.monitor_dir = self.project_root / "src" / "gs2026" / "monitor"
        self.analysis_dir = self.project_root / "src" / "gs2026" / "analysis" / "worker" / "message" / "deepseek"
        
        # 初始化监控器
        self._monitor = get_process_monitor()
        self._monitor.start_monitoring()
        
        # 注册全局状态变更回调
        self._monitor.on_status_change("*", self._on_process_status_change)
    
    def _on_process_status_change(self, process_id: str, status: str, info):
        """进程状态变更回调"""
        logger.info(f"Process status changed: {process_id} -> {status}")
        
        # 更新本地状态
        if process_id in self.processes:
            if status == "stopped":
                self.processes[process_id] = None
        
        # 更新服务状态
        if process_id in self.services:
            if status == "stopped":
                self.services[process_id] = None
        
        # 更新分析服务状态
        if process_id in self.analysis_services:
            if status == "stopped":
                self.analysis_services[process_id] = None
    
    def _is_process_running(self, pid: int) -> bool:
        """检查进程是否仍在运行"""
        try:
            proc = psutil.Process(pid)
            return proc.is_running()
        except psutil.NoSuchProcess:
            return False
    
    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def _register_process(self, process_id: str, pid: int, process_type: str, 
                          meta: Dict = None) -> bool:
        """
        注册进程到监控系统
        
        Args:
            process_id: 进程标识
            pid: 系统PID
            process_type: 进程类型
            meta: 额外元数据
        
        Returns:
            bool
        """
        return self._monitor.register(
            process_id=process_id,
            pid=pid,
            process_type=process_type,
            meta=meta or {}
        )
    
    def _unregister_process(self, process_id: str) -> bool:
        """注销进程"""
        return self._monitor.unregister(process_id)
    
    def _stop_system_process(self, pid: int) -> bool:
        """停止系统进程"""
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            
            # 等待进程结束
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
            
            return True
        except psutil.NoSuchProcess:
            return True  # 进程已不存在
        except Exception as e:
            logger.error(f"Failed to stop process PID={pid}: {e}")
            return False
    
    def _stop_process(self, process_key: str) -> Dict:
        """停止进程（通用方法）"""
        process_info = self.processes.get(process_key)
        
        if not process_info:
            return {'success': False, 'message': '进程未运行'}
        
        pid = process_info.get('pid')
        
        if self._stop_system_process(pid):
            self.processes[process_key] = None
            self._unregister_process(process_key)
            return {'success': True, 'message': '进程已停止'}
        else:
            return {'success': False, 'message': '停止进程失败'}
    
    def get_process_status(self, process_id: str) -> Optional[Dict]:
        """
        获取进程状态（新接口）
        
        Args:
            process_id: 进程标识
        
        Returns:
            Dict or None
        """
        info = self._monitor.get_status(process_id)
        if info:
            return {
                'process_id': info.process_id,
                'pid': info.pid,
                'status': info.status,
                'is_running': self._monitor.is_running(process_id),
                'start_time': info.start_time,
                'last_heartbeat': info.last_heartbeat,
                'process_type': info.process_type,
                'meta': info.meta
            }
        return None
    
    def get_all_process_status(self) -> List[Dict]:
        """
        获取所有进程状态（新接口）
        
        Returns:
            List[Dict]
        """
        processes = self._monitor.get_all_processes()
        return [
            {
                'process_id': p.process_id,
                'pid': p.pid,
                'status': p.status,
                'is_running': self._monitor.is_running(p.process_id),
                'start_time': p.start_time,
                'last_heartbeat': p.last_heartbeat,
                'process_type': p.process_type
            }
            for p in processes
        ]
    
    def cleanup(self):
        """清理资源（在应用关闭时调用）"""
        self._monitor.stop_monitoring()


# 保持向后兼容的别名
ProcessManagerBase = ProcessManagerWithMonitor