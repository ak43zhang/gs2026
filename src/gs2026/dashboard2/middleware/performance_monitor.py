"""
API性能监控中间件 - 非侵入式

使用方法:
1. 在 app.py 中注册: PerformanceMonitor(app)
2. 或通过 settings.yaml 启用: performance_monitor.enabled: true

特性:
- 零侵入: 不修改任何业务代码
- 可插拔: 通过 settings.yaml 控制启用/禁用
- 低开销: 默认禁用，启用后也只记录最近1000条
"""

import os
import time
import threading
from flask import request, g, jsonify
from loguru import logger
import yaml
from pathlib import Path


def _load_perf_config():
    """从 settings.yaml 加载性能监控配置"""
    try:
        config_path = Path(__file__).parent.parent.parent.parent / 'configs' / 'settings.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('performance_monitor', {})
    except Exception as e:
        logger.warning(f"加载 performance_monitor 配置失败: {e}")
    return {}


class PerformanceMonitor:
    """
    API性能监控中间件 - 非侵入式
    
    使用Flask的before_request和after_request钩子，不修改任何业务代码
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, app=None, enabled=None):
        # 如果已经初始化过，只处理app注册
        if self._initialized:
            if app and self.enabled:
                self.init_app(app)
            return
        
        # 从 settings.yaml 加载配置
        perf_config = _load_perf_config()
        
        # 优先使用传入参数，其次环境变量，最后配置文件
        if enabled is None:
            enabled = os.environ.get('ENABLE_PERF_MONITOR')
            if enabled is not None:
                enabled = enabled == '1'
            else:
                enabled = perf_config.get('enabled', False)
        
        self.enabled = enabled
        self.metrics = []
        self.metrics_lock = threading.Lock()
        self.max_metrics = perf_config.get('max_metrics', 1000)
        self.slow_threshold_ms = perf_config.get('slow_threshold_ms', 500)
        self.log_slow_requests = perf_config.get('log_slow_requests', True)
        
        if app:
            self.init_app(app)
        
        self._initialized = True
    
    def init_app(self, app):
        """初始化Flask应用"""
        if not self.enabled:
            logger.info("[PerformanceMonitor] 已禁用，跳过初始化")
            return
        
        @app.before_request
        def before_request():
            g.perf_start_time = time.time()
            g.perf_db_queries = 0
            g.perf_db_time = 0
            g.perf_redis_queries = 0
            g.perf_redis_time = 0
        
        @app.after_request
        def after_request(response):
            if hasattr(g, 'perf_start_time'):
                duration = (time.time() - g.perf_start_time) * 1000
                
                # 记录性能指标
                metric = {
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'method': request.method,
                    'path': request.path,
                    'endpoint': request.endpoint,
                    'duration_ms': round(duration, 2),
                    'status_code': response.status_code,
                    'db_queries': getattr(g, 'perf_db_queries', 0),
                    'db_time_ms': round(getattr(g, 'perf_db_time', 0), 2),
                    'redis_queries': getattr(g, 'perf_redis_queries', 0),
                    'redis_time_ms': round(getattr(g, 'perf_redis_time', 0), 2),
                }
                
                with self.metrics_lock:
                    self.metrics.append(metric)
                    # 只保留最近N条
                    if len(self.metrics) > self.max_metrics:
                        self.metrics = self.metrics[-self.max_metrics:]
                
                # 慢查询日志（>500ms）
                if duration > self.slow_threshold_ms:
                    logger.warning(
                        f"[SlowAPI] {request.method} {request.path} | "
                        f"{duration:.2f}ms | DB: {metric['db_queries']}q/{metric['db_time_ms']:.2f}ms | "
                        f"Redis: {metric['redis_queries']}q/{metric['redis_time_ms']:.2f}ms"
                    )
                
                # 添加响应头（方便前端查看）
                response.headers['X-Response-Time'] = f"{duration:.2f}ms"
            
            return response
        
        # 注册诊断API（不影响业务API）
        self._register_diag_apis(app)
        
        logger.info("[PerformanceMonitor] 已启用")
    
    def _register_diag_apis(self, app):
        """注册诊断API（独立路由，不影响业务）"""
        
        @app.route('/diag/performance', methods=['GET'])
        def diag_performance():
            """获取性能统计"""
            if not self.enabled:
                return jsonify({'enabled': False})
            
            with self.metrics_lock:
                metrics = self.metrics.copy()
            
            if not metrics:
                return jsonify({'enabled': True, 'message': '暂无数据'})
            
            # 统计计算
            durations = [m['duration_ms'] for m in metrics]
            db_times = [m['db_time_ms'] for m in metrics]
            redis_times = [m['redis_time_ms'] for m in metrics]
            
            # 计算P95
            sorted_durations = sorted(durations)
            p95_idx = int(len(sorted_durations) * 0.95)
            p95 = round(sorted_durations[p95_idx], 2) if len(sorted_durations) > 20 else None
            
            return jsonify({
                'enabled': True,
                'total_requests': len(metrics),
                'duration': {
                    'avg': round(sum(durations) / len(durations), 2),
                    'min': round(min(durations), 2),
                    'max': round(max(durations), 2),
                    'p95': p95,
                },
                'db_time': {
                    'avg': round(sum(db_times) / len(db_times), 2) if db_times else 0,
                    'total_queries': sum(m['db_queries'] for m in metrics),
                },
                'redis_time': {
                    'avg': round(sum(redis_times) / len(redis_times), 2) if redis_times else 0,
                    'total_queries': sum(m['redis_queries'] for m in metrics),
                },
                'slow_requests': [
                    m for m in sorted(metrics, key=lambda x: -x['duration_ms'])[:10]
                ],
            })
        
        @app.route('/diag/performance/reset', methods=['POST'])
        def diag_performance_reset():
            """重置统计数据"""
            with self.metrics_lock:
                self.metrics = []
            return jsonify({'success': True, 'message': '统计数据已重置'})
    
    def get_stats(self):
        """获取性能统计（用于测试和外部调用）"""
        if not self.enabled:
            return {'enabled': False}
        
        with self.metrics_lock:
            metrics = self.metrics.copy()
        
        if not metrics:
            return {'enabled': True, 'message': '暂无数据'}
        
        durations = [m['duration_ms'] for m in metrics]
        db_times = [m['db_time_ms'] for m in metrics]
        redis_times = [m['redis_time_ms'] for m in metrics]
        
        sorted_durations = sorted(durations)
        p95_idx = int(len(sorted_durations) * 0.95)
        p95 = round(sorted_durations[p95_idx], 2) if len(sorted_durations) > 20 else None
        
        return {
            'enabled': True,
            'total_requests': len(metrics),
            'duration': {
                'avg': round(sum(durations) / len(durations), 2),
                'min': round(min(durations), 2),
                'max': round(max(durations), 2),
                'p95': p95,
            },
            'db_time': {
                'avg': round(sum(db_times) / len(db_times), 2) if db_times else 0,
                'total_queries': sum(m['db_queries'] for m in metrics),
            },
            'redis_time': {
                'avg': round(sum(redis_times) / len(redis_times), 2) if redis_times else 0,
                'total_queries': sum(m['redis_queries'] for m in metrics),
            },
        }
    
    def reset(self):
        """重置统计数据"""
        with self.metrics_lock:
            self.metrics = []
        return {'success': True, 'message': '统计数据已重置'}


# 便捷函数：快速启用监控
def enable_performance_monitor(app):
    """
    快速启用性能监控
    
    使用环境变量控制：
    - set ENABLE_PERF_MONITOR=1  # Windows
    - export ENABLE_PERF_MONITOR=1  # Linux/Mac
    """
    return PerformanceMonitor(app)
