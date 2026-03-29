"""
数据分析模块路由
与数据采集同构
"""
from flask import Blueprint, jsonify, request
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gs2026.dashboard2.routes.analysis_modules import ANALYSIS_MODULES

try:
    from gs2026.dashboard.services.process_manager import process_manager
    PM_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] ProcessManager not available: {e}")
    process_manager = None
    PM_AVAILABLE = False

analysis_bp = Blueprint('analysis', __name__, url_prefix='/api/analysis')


@analysis_bp.route('/modules', methods=['GET'])
def get_modules():
    """获取所有分析模块"""
    response = jsonify({
        'success': True,
        'data': {'modules': ANALYSIS_MODULES}
    })
    # 禁用缓存
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@analysis_bp.route('/<module_id>/tasks', methods=['GET'])
def get_module_tasks(module_id):
    """获取模块任务列表"""
    module = ANALYSIS_MODULES.get(module_id)
    if not module:
        return jsonify({'success': False, 'error': 'Module not found'}), 404
    
    tasks = [
        {'id': task_id, **task_config}
        for task_id, task_config in module['tasks'].items()
    ]
    
    return jsonify({
        'success': True,
        'data': {'module': module_id, 'tasks': tasks}
    })


@analysis_bp.route('/<module_id>/start/<task_id>', methods=['POST'])
def start_task(module_id, task_id):
    """启动分析任务"""
    if not PM_AVAILABLE:
        return jsonify({'success': False, 'error': 'ProcessManager not available'}), 500
    
    module = ANALYSIS_MODULES.get(module_id)
    if not module:
        return jsonify({'success': False, 'error': 'Module not found'}), 404
    
    task = module['tasks'].get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    
    try:
        # 获取请求参数
        request_data = request.get_json() or {}
        print(f"[DEBUG] Start task request: {module_id}/{task_id}, data: {request_data}")
        
        # 分析任务使用监控服务方式启动（持续运行）
        # 对于 date_list 参数，需要特殊处理
        params = {}
        if 'date_list' in request_data:
            params['date_list'] = request_data['date_list']
        
        print(f"[DEBUG] Calling start_monitor_service with params: {params}")
        
        result = process_manager.start_monitor_service(
            service_id=f'analysis_{task_id}',
            script_name=task['file'],
            params=params
        )
        
        print(f"[DEBUG] start_monitor_service result: {result}")
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'process_id': result.get('process_id'),
                'pid': result.get('pid'),
                'message': result.get('message')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('message', '启动失败')
            }), 500
            
    except Exception as e:
        import traceback
        print(f"[ERROR] Exception in start_task: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@analysis_bp.route('/stop/<process_id>', methods=['POST'])
def stop_task(process_id):
    """停止分析任务"""
    if not PM_AVAILABLE:
        return jsonify({'success': False, 'error': 'ProcessManager not available'}), 500
    
    try:
        # 使用 stop_analysis_service 而不是 stop_process
        result = process_manager.stop_analysis_service(process_id)
        return jsonify({
            'success': result.get('success', True),
            'message': result.get('message', f'进程 {process_id} 已停止')
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] Exception in stop_task: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@analysis_bp.route('/status', methods=['GET'])
def get_status():
    """获取所有任务状态（包括分析任务和其他任务）"""
    if not PM_AVAILABLE:
        return jsonify({'success': False, 'error': 'ProcessManager not available'}), 500
    
    try:
        processes = []
        
        # 从监控系统获取所有进程（类似数据采集页面）
        if hasattr(process_manager, '_monitor'):
            all_processes = process_manager._monitor.get_all_processes(include_stopped=False)
            
            for proc in all_processes:
                processes.append({
                    'process_id': proc.process_id,
                    'service_id': proc.service_id,
                    'pid': proc.pid,
                    'status': proc.status,
                    'start_time': proc.start_time,
                    'process_type': proc.process_type,
                    'params': proc.params
                })
        
        return jsonify({
            'success': True,
            'data': {'processes': processes, 'count': len(processes)}
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] Exception in get_status: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500
