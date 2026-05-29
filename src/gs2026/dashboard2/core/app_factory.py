"""
应用工厂 - 创建Flask应用实例
- 配置加载
- 中间件注册
- 蓝图注册
- 初始化任务
"""

import logging
import yaml
from flask import Flask, render_template, redirect, request, session
from pathlib import Path
from datetime import timedelta

from gs2026.dashboard2.core.blueprint_registry import BlueprintRegistry
from gs2026.dashboard2.core.initializer import Initializer

logger = logging.getLogger('dashboard2.factory')


def create_app(config_name='default'):
    """
    创建Flask应用
    
    Args:
        config_name: 配置名称（development/production）
    
    Returns:
        Flask应用实例
    """
    # 1. 创建Flask实例
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent.parent / "templates"),
        static_folder=str(Path(__file__).parent.parent / "static")
    )
    
    # 2. 加载配置
    from gs2026.dashboard2.config import Config
    app.config.from_object(Config)
    logger.info(f"OK: config loaded: {config_name}")
    
    # 3. 配置认证系统
    _setup_auth(app)
    
    # 4. 注册中间件
    _register_middleware(app)
    
    # 5. 注册蓝图
    success, fail = BlueprintRegistry.register_all(app)
    logger.info(f"OK: blueprints registered: success={success}, fail={fail}")
    
    # 6. 注册页面路由
    _register_page_routes(app)
    
    # 7. 注册诊断API
    _register_diagnostic_routes(app)
    
    # 8. 执行初始化
    init_results = Initializer.run_all(app)
    
    # 9. 注册错误处理
    _register_error_handlers(app)
    
    logger.info("OK: app created")
    return app


def _setup_auth(app):
    """配置认证系统（保留原有逻辑）"""
    try:
        # core/app_factory.py 在 dashboard2/core/ 下，configs在根目录
        config_path = Path(__file__).parent.parent.parent.parent.parent / 'configs' / 'settings.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                auth_config = config.get('auth', {})
        else:
            auth_config = {}
    except Exception as e:
        logger.warning(f"auth config load failed: {e}")
        auth_config = {}
    
    # 设置session有效期
    session_days = auth_config.get('session_lifetime_days', 365)
    app.permanent_session_lifetime = timedelta(days=session_days)
    
    # before_request检查
    @app.before_request
    def require_login():
        if not auth_config.get('enabled', False):
            return
        # 排除不需要登录的路径
        excluded_paths = ('/login', '/logout', '/static', '/api/')
        if any(request.path.startswith(p) for p in excluded_paths):
            return
        if not session.get('logged_in'):
            return redirect('/login')
    
    logger.info(f"OK: auth system: {'enabled' if auth_config.get('enabled') else 'disabled'}")


def _register_middleware(app):
    """注册中间件（保留原有配置驱动逻辑）"""
    try:
        from gs2026.dashboard2.middleware.performance_monitor import PerformanceMonitor
        from gs2026.dashboard2.middleware.db_profiler import DBProfiler
        
        # 从settings.yaml读取配置
        config_path = Path(__file__).parent.parent.parent.parent.parent / 'configs' / 'settings.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                perf_config = config.get('performance_monitor', {})
                db_config = config.get('db_profiler', {})
        else:
            perf_config = {}
            db_config = {}
        
        # API性能监控
        perf_enabled = perf_config.get('enabled', False)
        PerformanceMonitor(app, enabled=perf_enabled)
        logger.info(f"OK: API perf monitor: {'enabled' if perf_enabled else 'disabled'}")
        
        # 数据库分析器
        db_enabled = db_config.get('enabled', False)
        if db_enabled:
            try:
                # 创建 SQLAlchemy engine
                from sqlalchemy import create_engine
                from gs2026.dashboard2.config import Config
                engine = create_engine(Config.MYSQL_URI)
                DBProfiler(engine, enabled=db_enabled)
                logger.info(f"OK: DB profiler: enabled")
            except Exception as db_e:
                logger.warning(f"WARN: DB profiler init failed: {db_e}")
        else:
            logger.info(f"OK: DB profiler: disabled")
        
    except Exception as e:
        logger.warning(f"WARN: middleware register failed: {e}")


def _register_page_routes(app):
    """注册页面路由（保留原有路由）"""
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/collection')
    def collection():
        return render_template('collection.html')
    
    @app.route('/analysis')
    def analysis():
        return render_template('analysis.html')
    
    @app.route('/reports')
    def reports():
        return render_template('reports.html')
    
    @app.route('/monitor')
    def monitor():
        # 加载前端性能监控配置
        frontend_perf_config = {'enabled': False}
        try:
            config_path = Path(__file__).parent.parent.parent.parent.parent / 'configs' / 'settings.yaml'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    frontend_perf_config = config.get('frontend_perf', {'enabled': False})
        except Exception:
            pass
        # 加载买点条件配置（每次渲染读取最新文件）
        import json
        bp_conditions = []
        try:
            bp_json_path = Path(__file__).parent.parent / 'config' / 'bp_conditions.json'
            with open(bp_json_path, 'r', encoding='utf-8') as f:
                bp_data = json.load(f)
                bp_conditions = bp_data.get('conditions', [])
        except Exception as e:
            print(f'[MONITOR] 加载bp_conditions.json失败: {e}')
        return render_template('monitor.html', frontend_perf_config=frontend_perf_config, bp_conditions=bp_conditions)
    
    @app.route('/news')
    def news():
        return render_template('news.html')
    
    @app.route('/stock-picker')
    def stock_picker():
        return render_template('stock_picker.html')
    
    @app.route('/performance')
    def performance():
        return render_template('performance.html')
    
    @app.route('/scheduler')
    def scheduler():
        return render_template('scheduler.html')
    
    @app.route('/chart/<bond_code>/<stock_code>')
    def chart(bond_code, stock_code):
        date = request.args.get('date', '')
        return render_template('chart.html', 
                               bond_code=bond_code, 
                               stock_code=stock_code,
                               date=date)
    
    logger.info("OK: page routes registered")


def _register_diagnostic_routes(app):
    """注册诊断API（保留原有功能）"""
    try:
        from gs2026.dashboard2.middleware.db_profiler import DBProfiler
        profiler = DBProfiler()
        
        @app.route('/diag/db', methods=['GET'])
        def diag_db():
            return profiler.get_stats()
        
        @app.route('/diag/db/reset', methods=['POST'])
        def diag_db_reset():
            return profiler.reset()
        
        logger.info("OK: diag API registered: /diag/db")
    except Exception as e:
        logger.warning(f"WARN: diag API register failed: {e}")


def _register_error_handlers(app):
    """注册错误处理器（简化版，不依赖模板）"""
    @app.errorhandler(404)
    def not_found(e):
        # 忽略favicon请求，不记录日志
        if request.path == '/favicon.ico':
            return '', 404
        # API请求返回JSON，页面请求返回简单HTML
        if request.path.startswith('/api/'):
            return {'error': 'Not found', 'path': request.path}, 404
        return f'<h1>404 Not Found</h1><p>{request.path}</p>', 404
    
    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"500: {e}")
        if request.path.startswith('/api/'):
            return {'error': 'Internal server error'}, 500
        return '<h1>500 Internal Server Error</h1>', 500
    
    logger.info("OK: error handlers registered")
