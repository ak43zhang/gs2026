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
