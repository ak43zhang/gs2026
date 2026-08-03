"""
过滤API

提供前后端统一的过滤接口
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import time

from ...common.pipeline import FilterConfig, UnifiedPipeline
from ...common.pipeline.cache import IndustryRankCache

api = Blueprint('filter_api', __name__)


@api.route('/api/filter/stock', methods=['POST'])
def filter_stock():
    """
    股票过滤API
    
    请求体:
    {
        "date": "20260803",
        "time": "10:00:00",
        "skip_filter": false,  // 可选，true时返回原始数据
        "config": {
            "stock_industry": "银行",
            "stock_topn_sectors": 5,
            "stock_topn_window": 10,
            ...
        }
    }
    
    响应:
    {
        "success": true,
        "data": [...],
        "filtered": true,
        "performance": {
            "elapsed_ms": 45.2,
            "input_count": 100,
            "output_count": 20
        }
    }
    """
    try:
        data = request.json or {}
        
        # 参数解析
        date = data.get('date')
        time_str = data.get('time')
        skip_filter = data.get('skip_filter', False)
        config_dict = data.get('config', {})
        
        # 获取原始数据（从data_service）
        from ...dashboard.services.data_service import DataService
        data_service = DataService()
        
        if skip_filter:
            # 显示全部模式
            raw_data = data_service.get_stock_ranking(date, time_str)
            return jsonify({
                'success': True,
                'data': raw_data,
                'filtered': False,
                'total': len(raw_data)
            })
        
        # 构建配置
        config = FilterConfig.from_dict(config_dict)
        
        # 获取原始数据
        raw_data = data_service.get_stock_ranking(date, time_str)
        
        # 执行过滤
        pipeline = UnifiedPipeline(config)
        start_time = time.perf_counter()
        filtered_data = pipeline.filter_stocks(raw_data, monitor_performance=True)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # 获取性能统计
        stats = pipeline.get_performance_stats()
        
        return jsonify({
            'success': True,
            'data': filtered_data,
            'filtered': True,
            'total': len(filtered_data),
            'performance': {
                'elapsed_ms': round(elapsed_ms, 2),
                'input_count': len(raw_data),
                'output_count': len(filtered_data),
                'details': stats
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"股票过滤失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api.route('/api/filter/bond', methods=['POST'])
def filter_bond():
    """
    债券过滤API
    
    类似股票过滤API
    """
    try:
        data = request.json or {}
        
        date = data.get('date')
        time_str = data.get('time')
        skip_filter = data.get('skip_filter', False)
        config_dict = data.get('config', {})
        
        from ...dashboard.services.data_service import DataService
        data_service = DataService()
        
        if skip_filter:
            raw_data = data_service.get_bond_ranking(date, time_str)
            return jsonify({
                'success': True,
                'data': raw_data,
                'filtered': False,
                'total': len(raw_data)
            })
        
        config = FilterConfig.from_dict(config_dict)
        raw_data = data_service.get_bond_ranking(date, time_str)
        
        pipeline = UnifiedPipeline(config)
        start_time = time.perf_counter()
        filtered_data = pipeline.filter_bonds(raw_data, monitor_performance=True)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        stats = pipeline.get_performance_stats()
        
        return jsonify({
            'success': True,
            'data': filtered_data,
            'filtered': True,
            'total': len(filtered_data),
            'performance': {
                'elapsed_ms': round(elapsed_ms, 2),
                'input_count': len(raw_data),
                'output_count': len(filtered_data),
                'details': stats
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"债券过滤失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api.route('/api/filter/compare', methods=['POST'])
def filter_compare():
    """
    对比测试专用API
    
    同时返回股票和债券的过滤结果
    """
    try:
        data = request.json or {}
        
        stocks = data.get('stocks', [])
        bonds = data.get('bonds', [])
        config_dict = data.get('config', {})
        
        config = FilterConfig.from_dict(config_dict)
        pipeline = UnifiedPipeline(config)
        
        # 过滤
        filtered_stocks = pipeline.filter_stocks(stocks, monitor_performance=False)
        filtered_bonds = pipeline.filter_bonds(bonds, monitor_performance=False)
        
        return jsonify({
            'success': True,
            'data': {
                'stocks': filtered_stocks,
                'bonds': filtered_bonds,
                'stock_count': len(filtered_stocks),
                'bond_count': len(filtered_bonds)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"对比过滤失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api.route('/api/filter/config', methods=['POST'])
def update_filter_config():
    """
    更新过滤配置（热更新）
    
    用于切换前后端过滤模式
    """
    try:
        data = request.json or {}
        
        # 切换前后端过滤模式
        use_backend = data.get('USE_BACKEND_FILTER')
        if use_backend is not None:
            current_app.config['USE_BACKEND_FILTER'] = bool(use_backend)
            return jsonify({
                'success': True,
                'message': f"已切换到 {'后端' if use_backend else '前端'} 过滤",
                'USE_BACKEND_FILTER': bool(use_backend)
            })
        
        return jsonify({
            'success': False,
            'error': '无效的配置参数'
        }), 400
        
    except Exception as e:
        current_app.logger.error(f"更新配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api.route('/api/filter/cache/clear', methods=['POST'])
def clear_cache():
    """清除行业排名缓存"""
    IndustryRankCache.clear()
    return jsonify({
        'success': True,
        'message': '缓存已清除'
    })
