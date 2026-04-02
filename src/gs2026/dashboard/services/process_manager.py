"""
进程管理器 - 管理数据采集、AI分析、监控等后台进程

特性：
- 集成 Redis 进程监控
- 自动检测进程状态
- 支持进程保活
"""
import subprocess
import psutil
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from gs2026.dashboard.services.process_monitor_adapter import ProcessManagerWithMonitor


class ProcessManager(ProcessManagerWithMonitor):
    """进程管理器（带Redis监控）"""
    
    def __init__(self):
        super().__init__()
        
        # 存储进程信息（保留原有结构）
        self.processes = {
            'collection': None,
            'analysis': None,
            'monitor': None
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
            
            # 注册到监控系统
            self._register_process(
                process_id='collection',
                pid=proc.pid,
                process_type='collection',
                meta={'dates': dates, 'script': str(script_path)}
            )
            
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
            
            # 注册到监控系统
            self._register_process(
                process_id='analysis',
                pid=proc.pid,
                process_type='analysis',
                meta={'script': str(temp_script)}
            )
            
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
            
            # 注册到监控系统
            self._register_process(
                process_id='monitor',
                pid=proc.pid,
                process_type='monitor',
                meta={'script': str(script_path)}
            )
            
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
            
            # 从监控系统注销
            self._unregister_process(name)
            
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
    
    def start_service(self, service_id: str, filename: str, max_instances: int = 5) -> Dict:
        """启动指定监控服务（支持多开）"""
        try:
            script_path = self.monitor_dir / filename
            if not script_path.exists():
                return {'success': False, 'message': f'脚本不存在: {script_path}'}
            
            # 检查最大实例数
            if not self._check_max_instances(service_id, max_instances):
                return {'success': False, 'message': f'{service_id} 已达到最大实例数限制 ({max_instances})'}
            
            # 生成实例ID
            process_id, instance_id = self._generate_instance_id(service_id)
            
            # 启动进程（独立进程，父进程退出不影响子进程）
            proc = subprocess.Popen(
                [self.python_exe, str(script_path)],
                cwd=str(self.project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
            
            # 保存到本地状态
            self.services[process_id] = {
                'pid': proc.pid,
                'start_time': self._get_current_time(),
                'service_id': service_id,
                'instance_id': instance_id
            }
            
            # 注册到监控系统
            self._register_process(
                process_id=process_id,
                service_id=service_id,
                instance_id=instance_id,
                pid=proc.pid,
                process_type='monitor_service',
                params={'filename': filename},
                meta={'service_id': service_id, 'filename': filename, 'instance_id': instance_id}
            )
            
            return {
                'success': True, 
                'message': f'{service_id} 已启动', 
                'pid': proc.pid,
                'process_id': process_id
            }
        except Exception as e:
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    def stop_service(self, process_id: str) -> Dict:
        """停止指定监控服务实例"""
        proc_info = self.services.get(process_id)
        
        # 尝试从监控系统获取（使用 get_process 而不是 get_status）
        if not proc_info and hasattr(self, '_monitor') and self._monitor:
            try:
                process_info = self._monitor.get_process(process_id)
                if process_info:
                    proc_info = {'pid': getattr(process_info, 'pid', None)}
            except Exception as e:
                print(f"[DEBUG] Error getting process from monitor: {e}")
        
        # 如果还是找不到，尝试通过 PID 前缀匹配
        if not proc_info:
            # 提取 service_id（去掉日期和后缀）
            service_id_prefix = process_id.rsplit('_', 2)[0] if '_' in process_id else process_id
            print(f"[DEBUG] Trying to find by prefix: {service_id_prefix}")
            
            # 在 self.services 中查找匹配的进程
            for sid, info in self.services.items():
                if sid.startswith(service_id_prefix) and info and info.get('pid'):
                    print(f"[DEBUG] Found matching process: {sid}")
                    proc_info = info
                    process_id = sid  # 更新 process_id 为实际找到的 ID
                    break
            
            # 在 Redis 中查找
            if not proc_info and hasattr(self, '_monitor') and self._monitor:
                try:
                    all_processes = self._monitor.get_all_processes(include_stopped=False)
                    for proc in all_processes:
                        sid = getattr(proc, 'process_id', '')
                        if sid.startswith(service_id_prefix):
                            print(f"[DEBUG] Found matching process in Redis: {sid}")
                            proc_info = {'pid': getattr(proc, 'pid', None)}
                            process_id = sid
                            break
                except Exception as e:
                    print(f"[DEBUG] Error searching in Redis: {e}")
        
        if not proc_info or not proc_info.get('pid'):
            return {'success': False, 'message': f'进程 {process_id} 不存在或未运行'}
        
        try:
            pid = proc_info['pid']
            print(f"[DEBUG] Stopping PID: {pid}")
            
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
            
            # 从本地状态移除
            if process_id in self.services:
                self.services[process_id] = None
            
            # 从监控系统注销
            try:
                self._unregister_process(process_id)
            except:
                pass
            
            return {'success': True, 'message': f'{process_id} 已停止'}
        except Exception as e:
            print(f"[ERROR] Exception in stop_service: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'停止失败: {str(e)}'}

    # stop_process 是 stop_service 的别名（兼容 Dashboard2）
    stop_process = stop_service

    def start_monitor_service(self, service_id: str, script_name: str, params: Dict = None) -> Dict:
        """启动监控服务（Dashboard2 兼容）- 支持分析任务和消息采集"""
        params = params or {}
        
        print(f"[DEBUG] start_monitor_service: service_id={service_id}, script_name={script_name}")
        
        # 分析任务使用 analysis 目录
        if script_name.startswith('analysis/'):
            print(f"[DEBUG] Matched analysis task")
            return self._start_analysis_service(service_id, script_name, params)
        
        # 消息采集任务使用 collection/news 目录
        # 支持带 news/ 前缀或不带前缀的脚本名
        news_scripts = ['collection_message.py', 'cls_history.py', 'dicj_yckx.py', 
                       'hot_api.py', 'xhcj.py', 'zqsb_rmcx.py']
        in_list = script_name in news_scripts
        ends_with = [script_name.endswith(f'news/{s}') for s in news_scripts]
        is_news = in_list or any(ends_with)
        print(f"[DEBUG] news_scripts check: in_list={in_list}, ends_with={ends_with}, is_news={is_news}, script_name={script_name}")
        if is_news:
            # 提取纯文件名（去掉 news/ 前缀）
            pure_name = script_name.split('/')[-1] if '/' in script_name else script_name
            print(f"[DEBUG] Matched news task, pure_name={pure_name}")
            return self._start_news_service(service_id, pure_name, params)
        
        # 普通监控任务使用原有逻辑
        print(f"[DEBUG] Falling back to start_service")
        return self.start_service(service_id, script_name, max_instances=5)
    
    def _start_analysis_service(self, service_id: str, script_name: str, params: Dict) -> Dict:
        """启动分析服务（支持参数传递）"""
        try:
            # 构建脚本路径: analysis/worker/message/deepseek/xxx.py
            script_path = self.project_root / "src" / "gs2026" / script_name
            if not script_path.exists():
                return {'success': False, 'message': f'分析脚本不存在: {script_path}'}
            
            # 检查最大实例数
            if not self._check_max_instances(service_id, max_instances=5):
                return {'success': False, 'message': f'{service_id} 已达到最大实例数限制 (5)'}
            
            # 生成实例ID
            process_id, instance_id = self._generate_instance_id(service_id)
            
            # 构建命令行参数（将 params 转换为 JSON 字符串）
            import json
            cmd = [self.python_exe, str(script_path)]
            if params:
                # 将参数作为 JSON 字符串传递
                params_json = json.dumps(params)
                cmd.extend(['--params', params_json])
            
            # 启动进程（独立进程，父进程退出不影响子进程）
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
            
            # 保存到本地状态
            self.services[process_id] = {
                'pid': proc.pid,
                'start_time': self._get_current_time(),
                'service_id': service_id,
                'instance_id': instance_id
            }
            
            # 注册到监控系统
            self._register_process(
                process_id=process_id,
                service_id=service_id,
                instance_id=instance_id,
                pid=proc.pid,
                process_type='analysis_service',
                params=params,
                meta={'service_id': service_id, 'script_name': script_name, 'instance_id': instance_id}
            )
            
            return {
                'success': True, 
                'message': f'{service_id} 已启动', 
                'pid': proc.pid,
                'process_id': process_id
            }
        except Exception as e:
            import traceback
            print(f"[ERROR] Exception in _start_analysis_service: {e}")
            traceback.print_exc()
            return {'success': False, 'message': f'启动失败: {str(e)}'}

    def _start_news_service(self, service_id: str, script_name: str, params: Dict = None) -> Dict:
        """启动消息采集服务（collection/news 目录）"""
        try:
            # 构建脚本路径: collection/news/xxx.py
            script_path = self.project_root / "src" / "gs2026" / "collection" / "news" / script_name
            if not script_path.exists():
                return {'success': False, 'message': f'消息采集脚本不存在: {script_path}'}
            
            # 检查最大实例数
            if not self._check_max_instances(service_id, max_instances=5):
                return {'success': False, 'message': f'{service_id} 已达到最大实例数限制 (5)'}
            
            # 生成实例ID
            process_id, instance_id = self._generate_instance_id(service_id)
            
            # 启动进程（独立进程，父进程退出不影响子进程）
            proc = subprocess.Popen(
                [self.python_exe, str(script_path)],
                cwd=str(self.project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
            
            # 保存到本地状态
            self.services[process_id] = {
                'pid': proc.pid,
                'start_time': self._get_current_time(),
                'service_id': service_id,
                'instance_id': instance_id
            }
            
            # 注册到监控系统
            self._register_process(
                process_id=process_id,
                service_id=service_id,
                instance_id=instance_id,
                pid=proc.pid,
                process_type='news_service',
                params=params,
                meta={'service_id': service_id, 'script_name': script_name, 'instance_id': instance_id}
            )
            
            return {
                'success': True, 
                'message': f'{service_id} 已启动', 
                'pid': proc.pid,
                'process_id': process_id
            }
        except Exception as e:
            import traceback
            print(f"[ERROR] Exception in _start_news_service: {e}")
            traceback.print_exc()
            return {'success': False, 'message': f'启动失败: {str(e)}'}

    def start_collection_service(self, service_id: str, script_name: str, function_name: str = None, params: Dict = None) -> Dict:
        """启动采集服务（Dashboard2 兼容）"""
        params = params or {}
        
        # 如果没有指定函数名，使用监控服务方式启动
        if not function_name:
            return self.start_monitor_service(service_id, script_name, params)
        
        # 有函数名，使用包装脚本方式
        try:
            # 构建脚本路径
            if '/' in script_name:
                # 处理子目录路径（如 other/bond_zh_cov.py）
                script_path = self.project_root / "src" / "gs2026" / "collection" / script_name
            elif script_name in ['wencai_collection.py', 'zt_collection.py', 'base_collection.py', 
                              'bk_gn_collection.py', 'baostock_collection.py']:
                script_path = self.project_root / "src" / "gs2026" / "collection" / "base" / script_name
            elif script_name in ['collection_message.py', 'cls_history.py', 'dicj_yckx.py', 
                                'hot_api.py', 'xhcj.py', 'zqsb_rmcx.py']:
                script_path = self.project_root / "src" / "gs2026" / "collection" / "news" / script_name
            elif script_name in ['akshare_risk_history.py', 'notice_risk_history.py', 
                                'wencai_risk_history.py', 'wencai_risk_year_history.py']:
                script_path = self.project_root / "src" / "gs2026" / "collection" / "risk" / script_name
            else:
                script_path = self.monitor_dir / script_name
            
            if not script_path.exists():
                return {'success': False, 'message': f'脚本不存在: {script_path}'}
            
            # 生成包装脚本
            wrapper_code = self._generate_collection_wrapper(service_id, script_name, function_name, params)
            
            wrapper_name = f"run_{service_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
            wrapper_path = self.project_root / "temp" / wrapper_name
            wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(wrapper_path, 'w', encoding='utf-8') as f:
                f.write(wrapper_code)
            
            # 检查最大实例数
            if not self._check_max_instances(service_id, 5):
                return {'success': False, 'message': f'{service_id} 已达到最大实例数限制'}
            
            # 生成实例ID
            process_id, instance_id = self._generate_instance_id(service_id)
            
            # 使用 STARTUPINFO 隐藏窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            
            # 启动进程（独立进程，父进程退出不影响子进程）
            proc = subprocess.Popen(
                [self.python_exe, str(wrapper_path)],
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                startupinfo=startupinfo
            )
            
            # 保存到本地状态
            self.services[process_id] = {
                'pid': proc.pid,
                'start_time': self._get_current_time(),
                'service_id': service_id,
                'instance_id': instance_id,
                'wrapper_path': str(wrapper_path)
            }
            
            # 注册到监控系统
            self._register_process(
                process_id=process_id,
                service_id=service_id,
                instance_id=instance_id,
                pid=proc.pid,
                process_type='collection_service',
                params=params,
                meta={'service_id': service_id, 'script': str(script_path), 'wrapper': str(wrapper_path), 'function': function_name}
            )
            
            return {'success': True, 'process_id': process_id, 'pid': proc.pid, 'message': f'{service_id} 启动成功'}
        except Exception as e:
            import traceback
            print(f"[ERROR] start_collection_service: {e}")
            traceback.print_exc()
            return {'success': False, 'message': f'启动失败: {str(e)}'}

    def _generate_collection_wrapper(self, service_id: str, script_name: str, function_name: str, params: Dict) -> str:
        """生成采集包装脚本"""
        script_module = script_name.replace('.py', '')
        
        # 处理 other 目录的脚本（如 other/bond_zh_cov.py）
        if '/' in script_name:
            parts = script_name.split('/')
            subdir = parts[0]
            script_file = parts[1]
            script_module = script_file.replace('.py', '')
            script_path = f"src.gs2026.collection.{subdir}.{script_module}"
        elif script_name in ['wencai_collection.py', 'zt_collection.py', 'base_collection.py', 'bk_gn_collection.py', 'baostock_collection.py']:
            script_path = f"src.gs2026.collection.base.{script_module}"
        elif script_name in ['collection_message.py', 'cls_history.py', 'dicj_yckx.py', 'hot_api.py', 'xhcj.py', 'zqsb_rmcx.py']:
            script_path = f"src.gs2026.collection.news.{script_module}"
        elif script_name in ['akshare_risk_history.py', 'notice_risk_history.py', 'wencai_risk_history.py', 'wencai_risk_year_history.py']:
            script_path = f"src.gs2026.collection.risk.{script_module}"
        else:
            script_path = f"src.gs2026.collection.base.{script_module}"
        
        params_str = ', '.join([f"{k}={repr(v)}" for k, v in params.items()])
        
        # 使用简单字符串拼接，避免转义问题
        lines = [
            '#!/usr/bin/env python3',
            'import sys',
            'import os',
            'from pathlib import Path',
            '',
            '# 重定向输出到空设备',
            'if sys.platform == "win32":',
            '    sys.stdout = open(os.devnull, "w")',
            '    sys.stderr = open(os.devnull, "w")',
            '',
            '# 计算项目根目录（包装脚本在 temp/ 目录，需要向上3层到 gs2026 目录）',
            'PROJECT_ROOT = Path(__file__).parent.parent',
            'sys.path.insert(0, str(PROJECT_ROOT))',
            '',
            'import traceback',
            'from datetime import datetime',
            '',
            f'SERVICE_ID = "{service_id}"',
            f'FUNCTION_NAME = "{function_name}"',
            '',
            'def log(msg):',
            '    try:',
            '        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")',
            '        log_dir = PROJECT_ROOT / "logs" / "collection"',
            '        log_dir.mkdir(parents=True, exist_ok=True)',
            '        log_file = log_dir / (SERVICE_ID + ".log")',
            '        with open(log_file, "a", encoding="utf-8") as f:',
            '            f.write("[" + ts + "] " + str(msg) + chr(10))',
            '    except:',
            '        pass',
            '',
            'log("=" * 60)',
            'log("[INIT] 启动 " + SERVICE_ID)',
            'log("[INIT] 函数: " + FUNCTION_NAME)',
            '',
            'try:',
            f'    from {script_path} import {function_name}',
            '    log("[RUN] 调用 " + FUNCTION_NAME)',
            f'    {function_name}({params_str})',
            '    log("[EXIT] 正常退出")',
            'except Exception as e:',
            '    log("[ERROR] " + str(type(e).__name__) + ": " + str(e))',
            '    log(traceback.format_exc())',
            '    raise',
        ]
        
        return chr(10).join(lines) + chr(10)
    
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
    
    def start_analysis_service(self, service_id: str, config: Dict, params: Dict, max_instances: int = 5) -> Dict:
        """启动指定分析服务（支持多开）"""
        try:
            # 检查最大实例数
            if not self._check_max_instances(service_id, max_instances):
                return {'success': False, 'message': f'{config["name"]} 已达到最大实例数限制 ({max_instances})'}
            
            # 生成实例ID
            process_id, instance_id = self._generate_instance_id(service_id, params)
            
            # 构建启动脚本
            script_path = self.analysis_dir / config['file']
            if not script_path.exists():
                return {'success': False, 'message': f'脚本不存在: {script_path}'}
            
            # 生成包装脚本
            wrapper_code = self._generate_analysis_wrapper(service_id, config, params)
            wrapper_path = self.project_root / "temp" / f"run_{process_id}.py"
            wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            wrapper_path.write_text(wrapper_code, encoding='utf-8')
            
            # 后台启动
            proc = subprocess.Popen(
                [self.python_exe, str(wrapper_path)],
                cwd=str(self.project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self.analysis_services[process_id] = {
                'pid': proc.pid,
                'params': params,
                'start_time': self._get_current_time(),
                'service_id': service_id,
                'instance_id': instance_id
            }
            
            # 注册到监控系统
            self._register_process(
                process_id=process_id,
                service_id=service_id,
                instance_id=instance_id,
                pid=proc.pid,
                process_type='analysis_service',
                params=params,
                meta={'service_id': service_id, 'name': config['name'], 'params': params, 'instance_id': instance_id}
            )
            
            return {
                'success': True, 
                'message': f'{config["name"]} 已启动', 
                'pid': proc.pid,
                'process_id': process_id
            }
        except Exception as e:
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    def stop_analysis_service(self, process_id: str) -> Dict:
        """停止指定分析服务实例"""
        proc_info = self.analysis_services.get(process_id)
        
        # 尝试从监控系统获取
        if not proc_info:
            info = self._monitor.get_status(process_id)
            if info and info.pid:
                proc_info = {'pid': info.pid}
        
        # 如果还是找不到，尝试通过 PID 前缀匹配查找（关键修复！）
        if not proc_info:
            # 提取 service_id（去掉日期和后缀）
            service_id_prefix = process_id.rsplit('_', 2)[0] if '_' in process_id else process_id
            print(f"[DEBUG] Trying to find analysis process by prefix: {service_id_prefix}")
            
            # 在 self.analysis_services 中查找匹配的进程
            for sid, info in self.analysis_services.items():
                if sid.startswith(service_id_prefix) and info and info.get('pid'):
                    print(f"[DEBUG] Found matching analysis process: {sid}")
                    proc_info = info
                    process_id = sid
                    break
            
            # 在 Redis 中查找
            if not proc_info and hasattr(self, '_monitor') and self._monitor:
                try:
                    all_processes = self._monitor.get_all_processes(include_stopped=False)
                    for proc in all_processes:
                        sid = getattr(proc, 'process_id', '')
                        if sid.startswith(service_id_prefix):
                            print(f"[DEBUG] Found matching analysis process in Redis: {sid}")
                            proc_info = {'pid': getattr(proc, 'pid', None)}
                            process_id = sid
                            break
                except Exception as e:
                    print(f"[DEBUG] Error searching in Redis: {e}")
        
        if not proc_info or not proc_info.get('pid'):
            return {'success': False, 'message': f'{process_id} 未在运行或进程信息不完整'}
        
        try:
            pid = proc_info['pid']
            print(f"[DEBUG] Stopping analysis PID: {pid}")
            
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
            
            # 从本地状态移除
            if process_id in self.analysis_services:
                self.analysis_services[process_id] = None
            
            # 从监控系统注销
            self._unregister_process(process_id)
            
            return {'success': True, 'message': f'{process_id} 已停止'}
        except Exception as e:
            print(f"[ERROR] Exception in stop_analysis_service: {e}")
            import traceback
            traceback.print_exc()
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
            year = params.get('year', '2026')
            return make_wrapper(
                'from gs2026.analysis.worker.message.deepseek.deepseek_analysis_notice import timer_task_do_notice',
                'timer_task_do_notice',
                f'({polling_time}, "{year}")'
            )
        
        return ''

    def stopAll(self) -> Dict:
        """停止所有进程（通过PID强制停止）"""
        stopped_count = 0
        failed_count = 0
        
        # 1. 停止 self.services 中的进程
        for process_id, proc_info in list(self.services.items()):
            if proc_info and proc_info.get('pid'):
                try:
                    pid = proc_info['pid']
                    if self._is_process_running(pid):
                        try:
                            parent = psutil.Process(pid)
                            for child in parent.children(recursive=True):
                                try: child.terminate()
                                except: pass
                            parent.terminate()
                            gone, alive = psutil.wait_procs([parent], timeout=3)
                            if alive:
                                for p in alive: p.kill()
                        except psutil.NoSuchProcess:
                            pass
                    
                    self.services[process_id] = None
                    try: self._unregister_process(process_id)
                    except: pass
                    
                    stopped_count += 1
                except Exception as e:
                    print(f"[ERROR] Failed to stop {process_id}: {e}")
                    failed_count += 1
        
        # 2. 从 Redis 获取所有进程并停止
        if hasattr(self, '_monitor') and self._monitor:
            try:
                all_processes = self._monitor.get_all_processes(include_stopped=False)
                for proc in all_processes:
                    try:
                        pid = getattr(proc, 'pid', None)
                        process_id = getattr(proc, 'process_id', None)
                        if pid and self._is_process_running(pid):
                            try:
                                parent = psutil.Process(pid)
                                for child in parent.children(recursive=True):
                                    try: child.terminate()
                                    except: pass
                                parent.terminate()
                                gone, alive = psutil.wait_procs([parent], timeout=3)
                                if alive:
                                    for p in alive: p.kill()
                            except psutil.NoSuchProcess:
                                pass
                            
                            if process_id:
                                try: self._unregister_process(process_id)
                                except: pass
                            
                            stopped_count += 1
                    except Exception as e:
                        print(f"[ERROR] Failed to stop process from Redis: {e}")
                        failed_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to get processes from Redis: {e}")
        
        return {
            'success': True,
            'stopped': stopped_count,
            'failed': failed_count,
            'message': f'已停止 {stopped_count} 个进程，失败 {failed_count} 个'
        }


# 创建全局进程管理器实例
process_manager = ProcessManager()
