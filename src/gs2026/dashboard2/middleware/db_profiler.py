"""
数据库查询分析器 - 非侵入式

使用方法:
1. 在 data_service.py 中附加: DBProfiler().attach_to_engine(engine)
2. 或通过 settings.yaml 启用: db_profiler.enabled: true

特性:
- 零侵入: 通过SQLAlchemy事件监听，不修改任何查询代码
- 可插拔: 通过 settings.yaml 控制启用/禁用
- 低开销: 默认禁用，启用后只记录最近500条
"""

import os
import time
import threading
from sqlalchemy import event
from loguru import logger
import yaml
from pathlib import Path


def _load_db_profiler_config():
    """从 settings.yaml 加载数据库分析器配置"""
    try:
        # 尝试多种可能的路径
        possible_paths = [
            # 从 db_profiler.py 向上5层到项目根目录
            Path(__file__).parent.parent.parent.parent.parent / 'configs' / 'settings.yaml',
            # 从 db_profiler.py 向上4层（兼容旧路径）
            Path(__file__).parent.parent.parent.parent / 'configs' / 'settings.yaml',
            # 通过环境变量指定项目根目录
            Path(os.environ.get('PROJECT_ROOT', '')) / 'configs' / 'settings.yaml' if os.environ.get('PROJECT_ROOT') else None,
        ]
        
        for config_path in possible_paths:
            if config_path and config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    return config.get('db_profiler', {})
        
        logger.warning("未找到 settings.yaml 配置文件")
    except Exception as e:
        logger.warning(f"加载 db_profiler 配置失败: {e}")
    return {}


class DBProfiler:
    """
    数据库查询分析器 - 非侵入式
    
    通过SQLAlchemy事件监听捕获所有查询
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
    
    def __init__(self, engine=None, enabled=None, slow_threshold_ms=None):
        # 如果已经初始化过，只处理引擎附加
        if self._initialized:
            if engine and self.enabled:
                self.attach_to_engine(engine)
            return
        
        # 从 settings.yaml 加载配置
        profiler_config = _load_db_profiler_config()
        
        # 优先使用传入参数，其次环境变量，最后配置文件
        if enabled is None:
            enabled = os.environ.get('ENABLE_DB_PROFILER')
            if enabled is not None:
                enabled = enabled == '1'
            else:
                enabled = profiler_config.get('enabled', False)
        
        self.enabled = enabled
        self.slow_threshold_ms = slow_threshold_ms or profiler_config.get('slow_threshold_ms', 100)
        self.queries = []
        self.queries_lock = threading.Lock()
        self.max_queries = profiler_config.get('max_queries', 500)
        self.log_slow_queries = profiler_config.get('log_slow_queries', True)
        self._attached_engines = set()  # 已附加的引擎集合
        
        if engine:
            self.attach_to_engine(engine)
        
        self._initialized = True
    
    def attach_to_engine(self, engine):
        """附加到SQLAlchemy引擎"""
        if not self.enabled:
            logger.info("[DBProfiler] 已禁用，跳过引擎附加")
            return
        
        # 避免重复附加
        engine_id = id(engine)
        if engine_id in self._attached_engines:
            logger.debug(f"[DBProfiler] 引擎已附加，跳过")
            return
        
        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()
            # 记录完整SQL语句（最多1000字符）
            context._query_statement = statement[:1000] if statement else ""
        
        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            duration = (time.time() - context._query_start_time) * 1000
            
            query_info = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'statement': context._query_statement,
                'duration_ms': round(duration, 2),
                'parameters': str(parameters)[:100] if parameters else None,
            }
            
            with self.queries_lock:
                self.queries.append(query_info)
                if len(self.queries) > self.max_queries:
                    self.queries = self.queries[-self.max_queries:]
            
            # 慢查询日志
            if duration > self.slow_threshold_ms:
                logger.warning(
                    f"[SlowQuery] {duration:.2f}ms | {context._query_statement[:100]}..."
                )

                # 保存到数据库（异步，不阻塞）
                try:
                    from gs2026.dashboard2.services.slow_log_storage import SlowLogStorage
                    SlowLogStorage().save_slow_query_async({
                        'sql_statement': context._query_statement,
                        'duration_ms': round(duration, 2),
                        'parameters': parameters
                    })
                except Exception:
                    pass  # 保存失败不影响主流程
            
            # 累加到Flask g对象（供PerformanceMonitor使用）
            try:
                from flask import g
                if hasattr(g, 'perf_db_queries'):
                    g.perf_db_queries += 1
                    g.perf_db_time += duration
            except Exception:
                pass
        
        self._attached_engines.add(engine_id)
        logger.info(f"[DBProfiler] 已附加到引擎，慢查询阈值: {self.slow_threshold_ms}ms")
    
    def get_stats(self):
        """获取统计信息"""
        if not self.enabled:
            return {'enabled': False}
        
        with self.queries_lock:
            queries = self.queries.copy()
        
        if not queries:
            return {'enabled': True, 'message': '暂无数据'}
        
        durations = [q['duration_ms'] for q in queries]
        
        # 按语句分组统计
        stmt_stats = {}
        for q in queries:
            stmt = q['statement'][:50]  # 简化语句
            if stmt not in stmt_stats:
                stmt_stats[stmt] = {'count': 0, 'total_time': 0, 'max_time': 0}
            stmt_stats[stmt]['count'] += 1
            stmt_stats[stmt]['total_time'] += q['duration_ms']
            stmt_stats[stmt]['max_time'] = max(stmt_stats[stmt]['max_time'], q['duration_ms'])
        
        # 排序找出最慢的语句类型
        slow_stmts = sorted(
            [{'statement': k, **v, 'avg_time': round(v['total_time']/v['count'], 2)} 
             for k, v in stmt_stats.items()],
            key=lambda x: -x['total_time']
        )[:10]
        
        # 计算P95
        sorted_durations = sorted(durations)
        p95_idx = int(len(sorted_durations) * 0.95)
        p95 = round(sorted_durations[p95_idx], 2) if len(sorted_durations) > 20 else None
        
        return {
            'enabled': True,
            'total_queries': len(queries),
            'slow_threshold_ms': self.slow_threshold_ms,
            'duration': {
                'avg': round(sum(durations) / len(durations), 2),
                'min': round(min(durations), 2),
                'max': round(max(durations), 2),
                'p95': p95,
            },
            'slowest_statements': slow_stmts,
            'recent_slow_queries': [
                q for q in sorted(queries, key=lambda x: -x['duration_ms'])[:10]
            ],
        }
    
    def reset(self):
        """重置统计"""
        with self.queries_lock:
            self.queries = []
        return {'success': True, 'message': '统计数据已重置'}


# 便捷函数
def enable_db_profiler(engine=None):
    """
    快速启用数据库分析器
    
    使用环境变量控制：
    - set ENABLE_DB_PROFILER=1  # Windows
    - export ENABLE_DB_PROFILER=1  # Linux/Mac
    """
    profiler = DBProfiler()
    if engine:
        profiler.attach_to_engine(engine)
    return profiler
