"""
控制面板路由 - 启动/停止进程
"""
from flask import Blueprint, jsonify, request
from gs2026.dashboard.services.process_manager import ProcessManager

control_bp = Blueprint('control', __name__)
process_manager = ProcessManager()


@control_bp.route('/status', methods=['GET'])
def get_process_status():
    """获取所有进程状态"""
    try:
        status = process_manager.get_all_status()
        return jsonify({
            'success': True,
            'data': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/monitor-status', methods=['GET'])
def get_monitor_status():
    """获取Redis监控的进程状态（新接口）"""
    try:
        # 获取所有被监控的进程
        processes = process_manager.get_all_process_status()
        return jsonify({
            'success': True,
            'data': processes,
            'count': len(processes)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/start-collection', methods=['POST'])
def start_collection():
    """启动数据采集"""
    try:
        result = process_manager.start_collection()
        return jsonify({
            'success': result['success'],
            'message': result['message'],
            'pid': result.get('pid')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/stop-collection', methods=['POST'])
def stop_collection():
    """停止数据采集"""
    try:
        result = process_manager.stop_collection()
        return jsonify({
            'success': result['success'],
            'message': result['message']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/start-analysis', methods=['POST'])
def start_analysis():
    """启动AI分析（deepseek_analysis_event_driven）"""
    try:
        # 获取日期参数
        data = request.get_json() or {}
        dates = data.get('dates', ['2026-03-22'])  # 默认日期
        
        result = process_manager.start_analysis(dates)
        return jsonify({
            'success': result['success'],
            'message': result['message'],
            'pid': result.get('pid'),
            'dates': dates
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/stop-analysis', methods=['POST'])
def stop_analysis():
    """停止AI分析"""
    try:
        result = process_manager.stop_analysis()
        return jsonify({
            'success': result['success'],
            'message': result['message']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/start-monitor', methods=['POST'])
def start_monitor():
    """启动监控程序"""
    try:
        result = process_manager.start_monitor()
        return jsonify({
            'success': result['success'],
            'message': result['message'],
            'pid': result.get('pid')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/stop-monitor', methods=['POST'])
def stop_monitor():
    """停止监控程序"""
    try:
        result = process_manager.stop_monitor()
        return jsonify({
            'success': result['success'],
            'message': result['message']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========== 五个监控服务独立控制 ==========

SERVICE_MAP = {
    'stock': 'monitor_stock.py',
    'bond': 'monitor_bond.py',
    'industry': 'monitor_industry.py',
    'dp_signal': 'monitor_dp_signal.py',
    'gp_zq_signal': 'monitor_gp_zq_rising_signal.py'
}


@control_bp.route('/services-status', methods=['GET'])
def get_services_status():
    """获取五个监控服务的状态"""
    try:
        status = process_manager.get_services_status(SERVICE_MAP)
        return jsonify({
            'success': True,
            'data': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/start-service/<service>', methods=['POST'])
def start_service(service):
    """启动指定服务"""
    if service not in SERVICE_MAP:
        return jsonify({
            'success': False,
            'message': f'未知服务: {service}'
        }), 400
    
    try:
        result = process_manager.start_service(service, SERVICE_MAP[service])
        return jsonify({
            'success': result['success'],
            'message': result['message'],
            'pid': result.get('pid')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/stop-service/<service>', methods=['POST'])
def stop_service(service):
    """停止指定监控服务"""
    if service not in SERVICE_MAP:
        return jsonify({
            'success': False,
            'message': f'未知服务: {service}'
        }), 400
    
    try:
        result = process_manager.stop_service(service)
        return jsonify({
            'success': result['success'],
            'message': result['message']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/stop-service-instance/<process_id>', methods=['POST'])
def stop_service_instance(process_id):
    """停止指定监控服务实例（支持多开）"""
    try:
        result = process_manager.stop_service(process_id)
        return jsonify({
            'success': result['success'],
            'message': result['message']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@control_bp.route('/stop-analysis-instance/<process_id>', methods=['POST'])
def stop_analysis_instance(process_id):
    """停止指定分析服务实例（支持多开）"""
    try:
        result = process_manager.stop_analysis_service(process_id)
        return jsonify({
            'success': result['success'],
            'message': result['message']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========== 五个分析服务独立控制 ==========

ANALYSIS_MAP = {
    'event_driven': {
        'file': 'deepseek_analysis_event_driven.py',
        'name': '事件驱动分析',
        'params': [{'name': 'date_list', 'type': 'date_list', 'label': '分析日期', 'default': ''}]
    },
    'news_cls': {
        'file': 'deepseek_analysis_news_cls.py',
        'name': '财联社新闻分析',
        'params': [
            {'name': 'polling_time', 'type': 'number', 'label': '轮询间隔(秒)', 'default': 10},
            {'name': 'year', 'type': 'text', 'label': '年份', 'default': '2026'}
        ]
    },
    'news_combine': {
        'file': 'deepseek_analysis_news_combine.py',
        'name': '综合新闻分析',
        'params': [
            {'name': 'polling_time', 'type': 'number', 'label': '轮询间隔(秒)', 'default': 10},
            {'name': 'year', 'type': 'text', 'label': '年份', 'default': '2026'}
        ]
    },
    'news_ztb': {
        'file': 'deepseek_analysis_news_ztb.py',
        'name': '涨停板分析',
        'params': [{'name': 'date_list', 'type': 'date_list', 'label': '分析日期', 'default': ''}]
    },
    'notice': {
        'file': 'deepseek_analysis_notice.py',
        'name': '公告分析',
        'params': [{'name': 'polling_time', 'type': 'number', 'label': '轮询间隔(秒)', 'default': 1}]
    }
}


@control_bp.route('/analysis-config', methods=['GET'])
def get_analysis_config():
    """获取分析服务配置（参数信息）"""
    return jsonify({'success': True, 'data': ANALYSIS_MAP})


@control_bp.route('/analysis-status', methods=['GET'])
def get_analysis_status():
    """获取分析服务状态"""
    try:
        status = process_manager.get_analysis_status(ANALYSIS_MAP)
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@control_bp.route('/start-analysis/<service>', methods=['POST'])
def start_analysis_service(service):
    """启动指定分析服务"""
    if service not in ANALYSIS_MAP:
        return jsonify({'success': False, 'message': f'未知服务: {service}'}), 400
    
    try:
        params = request.json or {}
        result = process_manager.start_analysis_service(service, ANALYSIS_MAP[service], params)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@control_bp.route('/stop-analysis/<service>', methods=['POST'])
def stop_analysis_service(service):
    """停止指定分析服务"""
    if service not in ANALYSIS_MAP:
        return jsonify({'success': False, 'message': f'未知服务: {service}'}), 400
    
    try:
        result = process_manager.stop_analysis_service(service)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
