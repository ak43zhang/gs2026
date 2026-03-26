#!/usr/bin/env python3
"""
修复 process_manager.py - 添加 Dashboard2 方法（正确版本）
"""
import re

file_path = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard\services\process_manager.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 在文件末尾添加新方法
new_methods = '''

    # ========== Dashboard2 新增方法 ==========

    def start_monitor_service(self, service_id: str, script_name: str, params: Dict = None) -> Dict:
        """启动监控服务（直接执行脚本，无包装）"""
        params = params or {}
        try:
            script_path = self.monitor_dir / script_name
            if not script_path.exists():
                return {'success': False, 'message': f'脚本不存在: {script_path}'}
            
            # 检查最大实例数
            if not self._check_max_instances(service_id, 5):
                return {'success': False, 'message': f'{service_id} 已达到最大实例数限制'}
            
            # 生成实例ID
            process_id, instance_id = self._generate_instance_id(service_id)
            
            # 使用 STARTUPINFO 隐藏窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            
            # 启动进程（后台运行）
            proc = subprocess.Popen(
                [self.pythonw_exe, str(script_path)],
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
                startupinfo=startupinfo
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
                params={'filename': script_name},
                meta={'service_id': service_id, 'filename': script_name, 'instance_id': instance_id}
            )
            
            return {'success': True, 'message': f'{service_id} 已启动', 'pid': proc.pid, 'process_id': process_id}
        except Exception as e:
            import traceback
            print(f"[ERROR] start_monitor_service: {e}")
            traceback.print_exc()
            return {'success': False, 'message': f'启动失败: {str(e)}'}

    def start_collection_service(self, service_id: str, script_name: str, function_name: str = None, params: Dict = None) -> Dict:
        """启动采集服务（使用包装脚本）"""
        params = params or {}
        try:
            # 构建脚本路径
            if script_name in ['wencai_collection.py', 'zt_collection.py', 'base_collection.py', 
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
            
            # 如果没有指定函数名，使用监控服务方式启动
            if not function_name:
                return self.start_monitor_service(service_id, script_name, params)
            
            # 生成包装脚本
            wrapper_code = self._generate_collection_wrapper(service_id, script_name, function_name, params)
            
            wrapper_name = f"run_{service_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
            wrapper_path = self.project_root / "temp" / wrapper_name
            wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(wrapper_path, 'w', encoding='utf-8') as f:
                f.write(wrapper_code)
            
            # 使用 STARTUPINFO 隐藏窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            
            # 启动进程（后台运行）
            proc = subprocess.Popen(
                [self.pythonw_exe, str(wrapper_path)],
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
                startupinfo=startupinfo
            )
            
            # 生成进程ID
            process_id = f"{service_id}_{datetime.now().strftime('%Y%m%d')}_{self._generate_random_suffix()}"
            instance_id = process_id.split('_')[-1]
            
            # 记录进程信息
            self.services[process_id] = {
                'pid': proc.pid,
                'start_time': self._get_current_time(),
                'params': params,
                'wrapper_path': str(wrapper_path)
            }
            
            # 注册到监控系统
            self._register_process(
                process_id=process_id,
                service_id=service_id,
                instance_id=instance_id,
                pid=proc.pid,
                process_type='service',
                params=params,
                meta={'service_id': service_id, 'script': str(script_path), 'wrapper': str(wrapper_path), 'function': function_name}
            )
            
            return {'success': True, 'process_id': process_id, 'pid': proc.pid, 'message': f'{service_id} 启动成功'}
        except Exception as e:
            import traceback
            print(f"[ERROR] start_collection_service: {e}")
            traceback.print_exc()
            return {'success': False, 'message': f'启动失败: {str(e)}'}

    def stop_process(self, process_id: str) -> Dict:
        """停止指定进程"""
        # 检查主进程
        for main_key in ['collection', 'analysis', 'monitor']:
            if process_id == main_key:
                return self._stop_process(main_key)
        
        # 查找进程信息
        proc_info = self.services.get(process_id)
        if not proc_info and hasattr(self, '_monitor') and self._monitor:
            try:
                info = self._monitor.get_process(process_id)
                if info:
                    proc_info = {'pid': info.pid}
            except:
                pass
        
        if not proc_info:
            return {'success': False, 'message': f'进程 {process_id} 不存在'}
        
        try:
            pid = proc_info.get('pid')
            if pid and self._is_process_running(pid):
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    try: child.terminate()
                    except: pass
                parent.terminate()
                gone, alive = psutil.wait_procs([parent], timeout=3)
                if alive:
                    for p in alive: p.kill()
            
            self.services[process_id] = None
            try: self._unregister_process(process_id)
            except: pass
            
            try:
                wrapper_path = Path(proc_info.get('wrapper_path', ''))
                if wrapper_path.exists(): wrapper_path.unlink()
            except: pass
            
            return {'success': True, 'message': f'{process_id} 已停止'}
        except Exception as e:
            return {'success': False, 'message': f'停止失败: {str(e)}'}

    def _generate_collection_wrapper(self, service_id: str, script_name: str, function_name: str, params: Dict) -> str:
        """生成采集包装脚本（使用原始字符串避免转义问题）"""
        script_module = script_name.replace('.py', '')
        if script_name in ['wencai_collection.py', 'zt_collection.py', 'base_collection.py', 'bk_gn_collection.py', 'baostock_collection.py']:
            script_path = f"src.gs2026.collection.base.{script_module}"
        elif script_name in ['collection_message.py', 'cls_history.py', 'dicj_yckx.py', 'hot_api.py', 'xhcj.py', 'zqsb_rmcx.py']:
            script_path = f"src.gs2026.collection.news.{script_module}"
        elif script_name in ['akshare_risk_history.py', 'notice_risk_history.py', 'wencai_risk_history.py', 'wencai_risk_year_history.py']:
            script_path = f"src.gs2026.collection.risk.{script_module}"
        else:
            script_path = f"src.gs2026.collection.base.{script_module}"
        
        params_str = ', '.join([f"{k}={repr(v)}" for k, v in params.items()])
        
        # 使用原始字符串和字符串拼接，避免转义问题
        wrapper = '''#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# 重定向输出到空设备
if sys.platform == "win32":
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import traceback
from datetime import datetime

SERVICE_ID = "''' + service_id + '''"
FUNCTION_NAME = "''' + function_name + '''"

def log(msg):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_dir = PROJECT_ROOT / "logs" / "collection"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / (SERVICE_ID + ".log")
        with open(log_file, "a", encoding="utf-8") as f:
            line = "[" + ts + "] " + str(msg) + chr(10)
            f.write(line)
    except:
        pass

log("=" * 60)
log("[INIT] 启动 " + SERVICE_ID)
log("[INIT] 函数: " + FUNCTION_NAME)

try:
    from ''' + script_path + ''' import ''' + function_name + '''
    log("[RUN] 调用 " + FUNCTION_NAME)
    ''' + function_name + '''(''' + params_str + ''')
    log("[EXIT] 正常退出")
except Exception as e:
    log("[ERROR] " + str(type(e).__name__) + ": " + str(e))
    log(traceback.format_exc())
    raise
'''
        return wrapper

    def _generate_random_suffix(self, length: int = 4) -> str:
        import random
        import string
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
'''

# 先添加 pythonw_exe 属性
old_init = '''        # 项目根目录
        self.project_root = Path(__file__).parent.parent.parent.parent.parent
        self.python_exe = r"F:\\python312\\python.exe"'''

new_init = '''        # 项目根目录
        self.project_root = Path(__file__).parent.parent.parent.parent.parent
        self.python_exe = r"F:\\python312\\python.exe"
        self.pythonw_exe = r"F:\\python312\\pythonw.exe"
        if not Path(self.pythonw_exe).exists():
            self.pythonw_exe = self.python_exe'''

content = content.replace(old_init, new_init)

# 在文件末尾添加新方法
content = content.rstrip() + new_methods

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
