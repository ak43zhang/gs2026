"""
Dashboard2 Collection Routes - ProcessManager Integration
数据采集模块路由 - 集成ProcessManager
"""

from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入ProcessManager（使用单例模式）
try:
    from gs2026.dashboard.services.process_manager import process_manager
    PM_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Failed to import ProcessManager: {e}")
    process_manager = None
    PM_AVAILABLE = False

collection_bp = Blueprint('collection', __name__, url_prefix='/api/collection')

# 模块配置（与前端配置保持一致）
COLLECTION_MODULES = {
    'monitor': {
        'name': '开市采集',
        'icon': '👁️',
        'type': 'monitor',
        'tasks': {
            'stock': {'name': '股票监控', 'file': 'monitor_stock.py', 'path': 'gs2026.monitor'},
            'bond': {'name': '债券监控', 'file': 'monitor_bond.py', 'path': 'gs2026.monitor'},
            'industry': {'name': '行业监控', 'file': 'monitor_industry.py', 'path': 'gs2026.monitor'},
            'dp_signal': {'name': '大盘信号', 'file': 'monitor_dp_signal.py', 'path': 'gs2026.monitor'},
            'gp_zq_signal': {'name': '股债联动', 'file': 'monitor_gp_zq_rising_signal.py', 'path': 'gs2026.monitor'}
        }
    },
    'base': {
        'name': '基础采集',
        'icon': '📊',
        'type': 'collection',
        'tasks': {
            # 1. 涨停板数据
            'ztb': {
                'name': '涨停板数据',
                'file': 'zt_collection.py',
                'function': 'collect_ztb_query',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            # 2. 涨停炸板数据
            'zt_zb': {
                'name': '涨停炸板数据',
                'file': 'zt_collection.py',
                'function': 'collect_zt_zb_collection',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            # 3. 指数宽基
            'zskj': {
                'name': '指数宽基',
                'file': 'base_collection.py',
                'function': 'zskj',
                'params': []
            },
            # 4. 今日龙虎榜
            'today_lhb': {
                'name': '今日龙虎榜',
                'file': 'base_collection.py',
                'function': 'today_lhb',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            # 5. 融资融券
            'rzrq': {
                'name': '融资融券',
                'file': 'base_collection.py',
                'function': 'rzrq',
                'params': []
            },
            # 6. 公司动态
            'gsdt': {
                'name': '公司动态',
                'file': 'base_collection.py',
                'function': 'gsdt',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            # 7. 历史龙虎榜
            'history_lhb': {
                'name': '历史龙虎榜',
                'file': 'base_collection.py',
                'function': 'history_lhb',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            # 8. 通达信风险
            'risk_tdx': {
                'name': '通达信风险',
                'file': 'base_collection.py',
                'function': 'risk_tdx',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            # 9. 同花顺行业
            'industry_ths': {
                'name': '同花顺行业',
                'file': 'base_collection.py',
                'function': 'industry_ths',
                'params': []
            },
            # 10. 同花顺行业成分
            'industry_code_component_ths': {
                'name': '同花顺行业成分',
                'file': 'base_collection.py',
                'function': 'industry_code_component_ths',
                'params': []
            },
            # 11. Baostock数据 (保留备用)
            'baostock': {
                'name': 'Baostock数据(备用)',
                'file': 'baostock_collection.py',
                'function': 'get_baostock_collection',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            # 11.1 股票日数据(AKShare)
            'stock_daily_akshare': {
                'name': '股票日数据(AKShare)',
                'file': 'stock_daily_collection.py',
                'function': 'collect_stock_daily',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ],
                'kwargs': {'data_source': 'akshare', 'batch_size': 100}
            },
            # 11.2 股票日数据(ADATA)
            'stock_daily_adata': {
                'name': '股票日数据(ADATA)',
                'file': 'stock_daily_collection.py',
                'function': 'collect_stock_daily',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ],
                'kwargs': {'data_source': 'adata', 'batch_size': 100}
            },
            # 12. 问财基础数据
            'wencai_base': {
                'name': '问财基础数据',
                'file': 'wencai_collection.py',
                'function': 'collect_base_query',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True},
                    {'name': 'headless', 'type': 'boolean', 'label': '无头模式', 'default': True}
                ]
            },
            # 13. 问财热股数据
            'wencai_hot': {
                'name': '问财热股数据',
                'file': 'wencai_collection.py',
                'function': 'collect_popularity_query',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True},
                    {'name': 'headless', 'type': 'boolean', 'label': '无头模式', 'default': True}
                ]
            },
            # 14. 可转债base
            'bond_base': {
                'name': '可转债base',
                'file': 'other/bond_zh_cov.py',
                'function': 'get_bond',
                'params': []
            },
            # 15. 可转债daily
            'bond_daily': {
                'name': '可转债daily',
                'file': 'other/bond_zh_cov.py',
                'function': 'get_bond_daily',
                'params': []
            },
            # 16. 板块概念
            'bk_gn': {
                'name': '板块概念',
                'file': 'bk_gn_collection.py',
                'function': 'bk_gn_collect',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            }
        }
    },
    'news': {
        'name': '消息采集',
        'icon': '📰',
        'type': 'monitor',  # 监控类型：持续运行（使用run_daemon_task）
        'tasks': {
            'cls_history': {
                'name': '财联社消息',
                'file': 'news/cls_history.py',
                # 财联社使用run_daemon_task持续运行，不指定function
                'params': []  # 无参数
            },
            'collection_message': {
                'name': '综合消息',
                'file': 'news/collection_message.py',
                # 使用run_daemon_task持续运行，不指定function
                'params': []  # 无参数
            },
            'dicj_yckx': {
                'name': '第一财经',
                'file': 'news/dicj_yckx.py',
                # 使用run_daemon_task持续运行，不指定function
                'params': []  # 无参数
            },
            'xhcj': {
                'name': '新华财网',
                'file': 'news/xhcj.py',
                # 使用run_daemon_task持续运行，不指定function
                'params': []  # 无参数
            },
            'zqsb_rmcx': {
                'name': '人民财讯',
                'file': 'news/zqsb_rmcx.py',
                # 使用run_daemon_task持续运行，不指定function
                'params': []  # 无参数
            }
        }
    },
    'risk': {
        'name': '风险采集',
        'icon': '⚠️',
        'type': 'collection',
        'tasks': {
            'wencai_risk_daily': {
                'name': '问财风险-日',
                'file': 'wencai_risk_history.py',
                'function': 'wencai_risk_collect',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            'wencai_risk_year': {
                'name': '问财风险-年',
                'file': 'wencai_risk_year_history.py',
                'function': 'wencai_risk_year_collect',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            'notice_risk': {
                'name': '公告风险',
                'file': 'notice_risk_history.py',
                'function': 'notice_and_risk_collect',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            },
            'akshare_risk': {
                'name': 'Akshare风险',
                'file': 'akshare_risk_history.py',
                'function': 'akshare_risk_collect',
                'params': [
                    {'name': 'start_date', 'type': 'date', 'label': '开始日期', 'required': True},
                    {'name': 'end_date', 'type': 'date', 'label': '结束日期', 'required': True}
                ]
            }
        }
    }
}


@collection_bp.route('/modules', methods=['GET'])
def get_modules():
    """获取所有模块配置"""
    return jsonify({
        'success': True,
        'data': {'modules': COLLECTION_MODULES}
    })


@collection_bp.route('/<module_id>/tasks', methods=['GET'])
def get_module_tasks(module_id):
    """获取模块任务列表"""
    module = COLLECTION_MODULES.get(module_id)
    if not module:
        return jsonify({'success': False, 'error': 'Module not found'}), 404
    
    return jsonify({
        'success': True,
        'data': {
            'module': module_id,
            'tasks': [
                {'id': task_id, **task_config}
                for task_id, task_config in module['tasks'].items()
            ]
        }
    })


@collection_bp.route('/<module_id>/start/<task_id>', methods=['POST'])
def start_task(module_id, task_id):
    """启动任务"""
    if not PM_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'ProcessManager not available'
        }), 500
    
    module = COLLECTION_MODULES.get(module_id)
    if not module:
        return jsonify({'success': False, 'error': 'Module not found'}), 404
    
    task = module['tasks'].get(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    
    params = request.get_json() or {}
    
    # 调试日志
    print(f"[DEBUG] Starting task: {module_id}/{task_id}")
    print(f"[DEBUG] Task config: {task}")
    print(f"[DEBUG] Params: {params}")
    
    try:
        # 获取任务配置
        script_name = task['file']
        function_name = task.get('function')
        
        print(f"[DEBUG] script_name: {script_name}, function_name: {function_name}")
        
        # 根据模块类型选择启动方法
        if module['type'] == 'monitor':
            # 监控类任务 - 持续运行，调用 main 函数
            print(f"[DEBUG] Using start_monitor_service")
            result = process_manager.start_monitor_service(
                service_id=task_id,
                script_name=script_name,
                params=params
            )
        else:
            # 采集类任务（基础/消息/风险）- 批量执行，调用指定函数
            print(f"[DEBUG] Using start_collection_service")
            result = process_manager.start_collection_service(
                service_id=task_id,
                script_name=script_name,
                function_name=function_name,
                params=params
            )
        
        print(f"[DEBUG] Result: {result}")
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'process_id': result.get('process_id', f'{module_id}_{task_id}'),
                'pid': result.get('pid', 0),
                'message': result.get('message', f'{task["name"]} 启动成功')
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
        return jsonify({
            'success': False,
            'error': f'启动失败: {str(e)}'
        }), 500


@collection_bp.route('/stop/<process_id>', methods=['POST'])
def stop_task(process_id):
    """停止任务"""
    print(f"[DEBUG] API stop_task called: {process_id}")
    
    if not PM_AVAILABLE:
        print(f"[ERROR] ProcessManager not available")
        return jsonify({
            'success': False,
            'error': 'ProcessManager not available'
        }), 500
    
    try:
        result = process_manager.stop_process(process_id)
        print(f"[DEBUG] stop_process result: {result}")
        return jsonify({
            'success': result.get('success', True),
            'message': result.get('message', f'进程 {process_id} 已停止')
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] Exception in stop_task: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'停止失败: {str(e)}'
        }), 500


@collection_bp.route('/status', methods=['GET'])
def get_status():
    """获取所有任务状态（包括运行中和已完成的）"""
    if not PM_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'ProcessManager not available'
        }), 500
    
    try:
        # 获取所有进程（包括已停止的）
        processes = process_manager._monitor.get_all_processes(include_stopped=True) if hasattr(process_manager, '_monitor') else []
        
        # 过滤出最近的任务（24小时内）
        from datetime import datetime, timedelta
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        recent_processes = []
        for proc in processes:
            # ProcessInfo 是对象，使用属性访问
            start_time_str = getattr(proc, 'start_time', '')
            try:
                if start_time_str:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    if start_time < cutoff_time:
                        continue  # 跳过24小时前的任务
            except:
                pass  # 时间解析失败，保留任务
            
            # 从 service_id 提取模块信息
            service_id = getattr(proc, 'service_id', '')
            process_type = getattr(proc, 'process_type', '')
            
            # 根据 service_id 前缀判断模块类型
            module = 'unknown'
            if service_id.startswith('analysis_'):
                module = 'deepseek'  # 分析模块
            elif service_id in ['stock', 'bond', 'industry', 'dp_signal', 'gp_zq_signal']:
                module = 'monitor'  # 开市采集
            elif service_id in ['wencai_base', 'wencai_hot', 'ztb', 'zt_zb', 'zskj', 
                               'today_lhb', 'rzrq', 'gsdt', 'history_lhb', 'risk_tdx',
                               'industry_ths', 'industry_code_component_ths']:
                module = 'base'  # 基础采集
            elif service_id.startswith('news_') or service_id in ['collection_message', 'cls_history', 
                                                                   'dicj_yckx', 'hot_api', 'xhcj', 'zqsb_rmcx']:
                module = 'news'  # 消息采集
            elif service_id.startswith('risk_') or service_id in ['akshare_risk_history', 'notice_risk_history',
                                                                   'wencai_risk_history', 'wencai_risk_year_history']:
                module = 'risk'  # 风险采集
            
            recent_processes.append({
                'process_id': getattr(proc, 'process_id', ''),
                'pid': getattr(proc, 'pid', None),
                'service_id': service_id,
                'module': module,
                'start_time': getattr(proc, 'start_time', ''),
                'stop_time': getattr(proc, 'stop_time', ''),
                'status': getattr(proc, 'status', 'unknown'),
                'params': getattr(proc, 'params', {})
            })
        
        # 按开始时间倒序排列
        recent_processes.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        
        return jsonify({
            'success': True,
            'data': recent_processes
        })
    except Exception as e:
        import traceback
        print(f"[ERROR] Exception in get_status: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'获取状态失败: {str(e)}'
        }), 500


@collection_bp.route('/control/status', methods=['GET'])
def get_control_status():
    """
    获取控制面板状态（兼容原版 Dashboard）
    返回格式与原版一致
    """
    if not PM_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'ProcessManager not available'
        }), 500
    
    try:
        all_processes = process_manager.get_all_process_status() if hasattr(process_manager, 'get_all_process_status') else []
        
        status = {
            'collection': {'running': False, 'pid': None, 'start_time': None},
            'analysis': {'running': False, 'pid': None, 'start_time': None},
            'monitor': {'running': False, 'pid': None, 'start_time': None}
        }
        
        for proc in all_processes:
            process_id = proc.get('process_id', '')
            process_type = proc.get('process_type', '')
            
            if process_id in ['collection', 'analysis', 'monitor']:
                if process_id in status:
                    status[process_id] = {
                        'running': True,
                        'pid': proc.get('pid'),
                        'start_time': proc.get('start_time')
                    }
            elif process_type == 'service':
                pass
            elif process_type == 'analysis':
                pass
        
        any_running = any(s['running'] for s in status.values())
        
        return jsonify({
            'success': True,
            'data': status,
            'any_running': any_running,
            'count': sum(1 for s in status.values() if s['running'])
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取状态失败: {str(e)}'
        }), 500


@collection_bp.route('/health', methods=['GET'])
def health_check():
    """
    健康检查 - 返回系统状态
    用于首页显示 Redis 和数据库状态
    """
    try:
        # 检查 Redis（通过 process_monitor）
        redis_ok = False
        if hasattr(process_manager, '_monitor'):
            try:
                process_manager._monitor.get_all_processes()
                redis_ok = True
            except:
                redis_ok = False
        
        # 检查数据库
        db_ok = False
        try:
            from gs2026.utils import mysql_util
            from sqlalchemy import create_engine, text
            from gs2026.utils.config_util import get_config
            
            url = get_config("common.url")
            engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
            with engine.connect() as con:
                con.execute(text("SELECT 1"))
            db_ok = True
        except Exception as e:
            db_ok = False
        
        return jsonify({
            'success': True,
            'data': {
                'redis': {'status': 'connected' if redis_ok else 'disconnected', 'ok': redis_ok},
                'database': {'status': 'connected' if db_ok else 'disconnected', 'ok': db_ok}
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@collection_bp.route('/stop-all', methods=['POST'])
def stop_all():
    """停止所有任务"""
    if not PM_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'ProcessManager not available'
        }), 500
    
    try:
        result = process_manager.stop_all_processes()
        return jsonify({
            'success': result.get('success', True),
            'stopped': result.get('stopped', 0),
            'message': result.get('message', '所有任务已停止')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'停止失败: {str(e)}'
        }), 500
