"""
进程管理器 - 管理数据采集、AI分析、监控等后台进程
"""
import subprocess
import psutil
import time
from pathlib import Path
from datetime import datetime
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
        
        # 五个独立监控服务
        self.services = {}
        
        # 五个独立分析服务
        self.analysis_services = {}
        
        # 项目根目录
        self.project_root = Path(__file__).parent.parent.parent.parent.parent
        self.python_exe = r"F:\python312\python.exe"
        
        # monitor 目录
        self.monitor_dir = self.project_root / "src" / "gs2026" / "monitor"
        
        # analysis 目录
        self.analysis_dir = self.project_root / "src" / "gs2026" / "analysis" / "worker" / "message" / "deepseek"
    
    def _is_process_running(self, pid: int) -> bool:
        """检查进程是否仍在运行"""
        try:
            proc = psutil.Process(pid)
            return proc.is_running()
        except psutil.NoSuchProcess:
            return False
    
    def start_collection(self, dates: List[str]) -> Dict:
        """启动数据采集"""
        if self.processes['collection'] and self._is_process_running(self.processes['collection']['pid']):
            return {'success': False, 'message': '数据采集已在运行中'}
        
        try:
            # 构建启动命令
            script_path = self.project_root / "src" / "gs2026" / "collection" / "main.py"
            
            # 启动进程
            proc = subprocess.Popen(
                [self.python_exe, str(script_path)] + dates,
                cwd=str(self.project_root),
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self.processes['collection'] = {
                'pid': proc.pid,
                'start_time': self._get_current_time(),
                'dates': dates
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

if __name__ == "__main__":
    analysis_event_driven({dates})
'''
            # 写入临时脚本
            temp_script = self.project_root / "temp_analysis.py"
            temp_script.write_text(script_content, encoding='utf-8')
            
            # 启动进程
            proc = subprocess.Popen(
                [self.python_exe, str(temp_script)],
                cwd=str(self.project_root),
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self.processes['analysis'] = {
                'pid': proc.pid,
                'start_time': self._get_current_time()
            }
            
            return {'success': True, 'message': 'AI分析已启动', 'pid': proc.pid}
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
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
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
            
            # 使用psutil终止进程树
            if self._is_process_running(pid):
                parent = psutil.Process(pid)
                # 先终止子进程
                for child in parent.children(recursive=True):
                    try:
                        child.terminate()
                    except:
                        pass
                # 再终止父进程
                parent.terminate()
                
                # 等待进程终止
                gone, alive = psutil.wait_procs([parent], timeout=3)
                if alive:
                    # 强制杀死
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
    
    # ========== 五个监控服务独立管理 ==========
    
    def get_services_status(self, service_map: Dict) -> Dict:
        """获取五个监控服务的状态"""
        status = {}
        for service_id, filename in service_map.items():
            proc_info = self.services.get(service_id)
            if proc_info and proc_info.get('pid'):
                if self._is_process_running(proc_info['pid']):
                    status[service_id] = {
                        'running': True,
                        'pid': proc_info['pid'],
                        'filename': filename
                    }
                else:
                    status[service_id] = {'running': False}
                    self.services[service_id] = None
            else:
                status[service_id] = {'running': False}
        return status
    
    def start_service(self, service_id: str, filename: str) -> Dict:
        """启动指定监控服务"""
        # 检查是否已在运行
        if service_id in self.services and self.services[service_id]:
            pid = self.services[service_id]['pid']
            if self._is_process_running(pid):
                return {'success': False, 'message': f'{service_id} 已在运行中，PID: {pid}'}
        
        try:
            script_path = self.monitor_dir / filename
            if not script_path.exists():
                return {'success': False, 'message': f'脚本不存在: {script_path}'}
            
            # 启动进程（创建新控制台窗口）
            proc = subprocess.Popen(
                [self.python_exe, str(script_path)],
                cwd=str(self.project_root),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            self.services[service_id] = {
                'pid': proc.pid,
                'start_time': self._get_current_time()
            }
            
            return {'success': True, 'message': f'{service_id} 已启动', 'pid': proc.pid}
        except Exception as e:
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    def stop_service(self, service_id: str) -> Dict:
        """停止指定监控服务"""
        proc_info = self.services.get(service_id)
        if not proc_info:
            return {'success': False, 'message': f'{service_id} 未在运行'}
        
        try:
            pid = proc_info['pid']
            if self._is_process_running(pid):
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    try:
                        child.terminate()
                    except:
                        pass
                parent.terminate()
                
                gone, alive = psutil.wait_procs([parent], timeout=3)
                if alive:
                    for p in alive:
                        p.kill()
            
            self.services[service_id] = None
            return {'success': True, 'message': f'{service_id} 已停止'}
        except Exception as e:
            return {'success': False, 'message': f'停止失败: {str(e)}'}
    
    # ========== 五个分析服务独立管理 ==========
    
    def get_analysis_status(self, analysis_map: Dict) -> Dict:
        """获取分析服务状态"""
        status = {}
        for service_id in analysis_map:
            proc_info = self.analysis_services.get(service_id)
            if proc_info and proc_info.get('pid'):
                if self._is_process_running(proc_info['pid']):
                    status[service_id] = {
                        'running': True,
                        'pid': proc_info['pid'],
                        'params': proc_info.get('params', {})
                    }
                else:
                    status[service_id] = {'running': False}
                    self.analysis_services[service_id] = None
            else:
                status[service_id] = {'running': False}
        return status
    
    def start_analysis_service(self, service_id: str, config: Dict, params: Dict) -> Dict:
        """启动指定分析服务"""
        # 检查是否已在运行
        if service_id in self.analysis_services and self.analysis_services[service_id]:
            pid = self.analysis_services[service_id]['pid']
            if self._is_process_running(pid):
                return {'success': False, 'message': f'{config["name"]} 已在运行中，PID: {pid}'}
        
        try:
            # 构建启动脚本（将参数传递给入口函数）
            script_path = self.analysis_dir / config['file']
            if not script_path.exists():
                return {'success': False, 'message': f'脚本不存在: {script_path}'}
            
            # 生成包装脚本，传递参数
            wrapper_code = self._generate_analysis_wrapper(service_id, config, params)
            wrapper_path = self.project_root / "temp" / f"run_{service_id}.py"
            wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            wrapper_path.write_text(wrapper_code, encoding='utf-8')
            
            # 后台启动（创建新控制台窗口，确保进程独立运行）
            proc = subprocess.Popen(
                [self.python_exe, str(wrapper_path)],
                cwd=str(self.project_root),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            self.analysis_services[service_id] = {
                'pid': proc.pid,
                'params': params,
                'start_time': self._get_current_time()
            }
            
            return {'success': True, 'message': f'{config["name"]} 已启动', 'pid': proc.pid}
        except Exception as e:
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    def stop_analysis_service(self, service_id: str) -> Dict:
        """停止指定分析服务"""
        proc_info = self.analysis_services.get(service_id)
        if not proc_info:
            return {'success': False, 'message': f'{service_id} 未在运行'}
        
        try:
            pid = proc_info['pid']
            if self._is_process_running(pid):
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    try:
                        child.terminate()
                    except:
                        pass
                parent.terminate()
                
                gone, alive = psutil.wait_procs([parent], timeout=3)
                if alive:
                    for p in alive:
                        p.kill()
            
            self.analysis_services[service_id] = None
            return {'success': True, 'message': f'{service_id} 已停止'}
        except Exception as e:
            return {'success': False, 'message': f'停止失败: {str(e)}'}
    
    def _generate_analysis_wrapper(self, service_id: str, config: Dict, params: Dict) -> str:
        """生成分析服务的启动包装脚本"""
        # 使用正斜杠，避免转义问题
        project_root = str(self.project_root).replace('\\', '/')
        
        # 统一的包装模板
        def make_wrapper(import_path: str, func_name: str, args_str: str) -> str:
            return f'''import sys
import traceback
import os
from pathlib import Path

# 确保路径设置正确（必须在导入其他模块之前）
PROJECT_ROOT = r"{project_root}"
SRC_PATH = os.path.join(PROJECT_ROOT, "src")

# 清除可能冲突的路径，确保 src 在最前面
if PROJECT_ROOT in sys.path:
    sys.path.remove(PROJECT_ROOT)
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_PATH)

# 创建日志目录
log_dir = Path(PROJECT_ROOT) / "logs" / "analysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "{service_id}.log"

def log(msg):
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{{msg}}]\\n")
    except:
        pass

log("=" * 60)
log(f"[INIT] 启动 {service_id}")
log(f"[INIT] PROJECT_ROOT: {{PROJECT_ROOT}}")
log(f"[INIT] SRC_PATH: {{SRC_PATH}}")
log(f"[INIT] sys.path[0:2]: {{sys.path[0:2]}}")

try:
    {import_path}
    from gs2026.utils.task_runner import run_daemon_task
    log("[RUN] 调用 run_daemon_task")
    # 使用 daemon=False 前台运行，防止进程退出
    run_daemon_task(target={func_name}, args={args_str}, daemon=False)
    log("[EXIT] 正常退出")
except Exception as e:
    log(f"[ERROR] {{type(e).__name__}}: {{str(e)}}")
    log(traceback.format_exc())
    raise
'''
        
        if service_id == 'event_driven':
            date_list = params.get('date_list', '')
            dates = [d.strip() for d in date_list.split(',') if d.strip()]
            return make_wrapper(
                'from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import analysis_event_driven',
                'analysis_event_driven',
                f'({dates},)'
            )
        
        elif service_id == 'news_cls':
            polling_time = int(params.get('polling_time', 10))
            year = params.get('year', '2026')
            return make_wrapper(
                'from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls',
                'time_task_do_cls',
                f'({polling_time}, "{year}")'
            )
        
        elif service_id == 'news_combine':
            polling_time = int(params.get('polling_time', 10))
            year = params.get('year', '2026')
            return make_wrapper(
                'from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_combine import time_task_do_combine',
                'time_task_do_combine',
                f'({polling_time},)'
            )
        
        elif service_id == 'news_ztb':
            date_list = params.get('date_list', '')
            dates = [d.strip() for d in date_list.split(',') if d.strip()]
            return make_wrapper(
                'from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_ztb import analysis_ztb',
                'analysis_ztb',
                f'({dates},)'
            )
        
        elif service_id == 'notice':
            polling_time = int(params.get('polling_time', 1))
            return make_wrapper(
                'from gs2026.analysis.worker.message.deepseek.deepseek_analysis_notice import timer_task_do_notice',
                'timer_task_do_notice',
                f'({polling_time},)'
            )
        
        return ''
