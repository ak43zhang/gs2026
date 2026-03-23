"""
进程管理服务 - 启动/停止外部程序
"""
import subprocess
import psutil
import os
import signal
from pathlib import Path
from typing import Dict, List, Optional


class ProcessManager:
    """进程管理器"""
    
    def __init__(self):
        # 存储进程信息
        self.processes = {
            'collection': None,  # 数据采集进程
            'analysis': None,    # AI分析进程
            'monitor': None      # 监控进程
        }
        
        # 项目根目录
        self.project_root = Path(__file__).parent.parent.parent.parent.parent
        self.python_exe = r"F:\python312\python.exe"
    
    def get_all_status(self) -> Dict:
        """获取所有进程状态"""
        status = {}
        for name, proc_info in self.processes.items():
            if proc_info and proc_info.get('pid'):
                # 检查进程是否还在运行
                if self._is_process_running(proc_info['pid']):
                    status[name] = {
                        'running': True,
                        'pid': proc_info['pid'],
                        'start_time': proc_info.get('start_time')
                    }
                else:
                    status[name] = {'running': False}
                    self.processes[name] = None
            else:
                status[name] = {'running': False}
        return status
    
    def _is_process_running(self, pid: int) -> bool:
        """检查进程是否在运行"""
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    def start_collection(self) -> Dict:
        """启动数据采集"""
        if self.processes['collection'] and self._is_process_running(self.processes['collection']['pid']):
            return {'success': False, 'message': '数据采集已在运行中'}
        
        try:
            # 启动数据采集脚本（根据实际情况修改路径）
            script_path = self.project_root / "src" / "gs2026" / "collection" / "main.py"
            
            proc = subprocess.Popen(
                [self.python_exe, str(script_path)],
                cwd=str(self.project_root),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            self.processes['collection'] = {
                'pid': proc.pid,
                'start_time': self._get_current_time()
            }
            
            return {'success': True, 'message': '数据采集已启动', 'pid': proc.pid}
        except Exception as e:
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    def stop_collection(self) -> Dict:
        """停止数据采集"""
        return self._stop_process('collection')
    
    def start_analysis(self, dates: List[str]) -> Dict:
        """启动AI分析 - 调用 deepseek_analysis_event_driven"""
        if self.processes['analysis'] and self._is_process_running(self.processes['analysis']['pid']):
            return {'success': False, 'message': 'AI分析已在运行中'}
        
        try:
            # 创建临时脚本调用 analysis_event_driven
            script_content = f'''
import sys
sys.path.insert(0, r"{self.project_root}")

from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import analysis_event_driven

# 执行分析
dates = {dates}
analysis_event_driven(dates)

# 保持进程运行
import time
while True:
    time.sleep(60)
'''
            # 写入临时文件
            temp_script = self.project_root / "temp_analysis.py"
            with open(temp_script, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            # 启动进程
            proc = subprocess.Popen(
                [self.python_exe, str(temp_script)],
                cwd=str(self.project_root),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            self.processes['analysis'] = {
                'pid': proc.pid,
                'start_time': self._get_current_time(),
                'dates': dates
            }
            
            return {'success': True, 'message': f'AI分析已启动，日期: {dates}', 'pid': proc.pid}
        except Exception as e:
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    def stop_analysis(self) -> Dict:
        """停止AI分析"""
        return self._stop_process('analysis')
    
    def start_monitor(self) -> Dict:
        """启动监控程序"""
        if self.processes['monitor'] and self._is_process_running(self.processes['monitor']['pid']):
            return {'success': False, 'message': '监控程序已在运行中'}
        
        try:
            # 启动监控脚本
            script_path = self.project_root / "src" / "gs2026" / "monitor" / "main.py"
            
            proc = subprocess.Popen(
                [self.python_exe, str(script_path)],
                cwd=str(self.project_root),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            self.processes['monitor'] = {
                'pid': proc.pid,
                'start_time': self._get_current_time()
            }
            
            return {'success': True, 'message': '监控程序已启动', 'pid': proc.pid}
        except Exception as e:
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    def stop_monitor(self) -> Dict:
        """停止监控程序"""
        return self._stop_process('monitor')
    
    def _stop_process(self, name: str) -> Dict:
        """停止指定进程"""
        proc_info = self.processes.get(name)
        if not proc_info:
            return {'success': False, 'message': f'{name} 未在运行'}
        
        try:
            pid = proc_info['pid']
            if self._is_process_running(pid):
                # 终止进程树
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    try:
                        child.terminate()
                    except:
                        pass
                parent.terminate()
                
                # 等待进程结束
                gone, alive = psutil.wait_procs([parent], timeout=3)
                if alive:
                    # 强制终止
                    for p in alive:
                        p.kill()
            
            self.processes[name] = None
            return {'success': True, 'message': f'{name} 已停止'}
        except Exception as e:
            return {'success': False, 'message': f'停止失败: {str(e)}'}
    
    def _get_current_time(self) -> str:
        """获取当前时间"""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
