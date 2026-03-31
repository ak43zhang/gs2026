"""
Dashboard2 - 主应用
整合原版监控功能和新版采集功能
"""

from flask import Flask, render_template, redirect, request
from pathlib import Path
import sys
import os

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gs2026.dashboard2.config import Config

# 导入性能监控中间件（非侵入式，默认禁用）
try:
    from gs2026.dashboard2.middleware.performance_monitor import PerformanceMonitor
    from gs2026.dashboard2.middleware.db_profiler import DBProfiler
    PERF_MONITOR_AVAILABLE = True
except ImportError as e:
    print(f"[PerfMonitor] 中间件导入失败: {e}")
    PERF_MONITOR_AVAILABLE = False

def create_app():
    """创建Flask应用"""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static")
    )
    app.config.from_object(Config)
    
    # 初始化性能监控中间件（非侵入式，通过 settings.yaml 控制）
    if PERF_MONITOR_AVAILABLE:
        # 从 settings.yaml 读取配置
        perf_config = {}
        db_profiler_config = {}
        try:
            import yaml
            config_path = Path(__file__).parent.parent.parent.parent / 'configs' / 'settings.yaml'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    perf_config = config.get('performance_monitor', {})
                    db_profiler_config = config.get('db_profiler', {})
        except Exception as e:
            print(f"[PerfMonitor] 加载配置失败: {e}")
        
        # API性能监控 - 默认禁用，通过 settings.yaml 启用
        perf_monitor_enabled = perf_config.get('enabled', False)
        PerformanceMonitor(app, enabled=perf_monitor_enabled)
        print(f"[PerfMonitor] API性能监控: {'已启用' if perf_monitor_enabled else '已禁用（在 configs/settings.yaml 中设置 performance_monitor.enabled: true 启用）'}")
        
        # 数据库分析器将在data_service中附加
        db_profiler_enabled = db_profiler_config.get('enabled', False)
        print(f"[PerfMonitor] 数据库分析器: {'已启用' if db_profiler_enabled else '已禁用（在 configs/settings.yaml 中设置 db_profiler.enabled: true 启用）'}")
    
    # 注册采集模块蓝图
    from gs2026.dashboard2.routes.collection import collection_bp
    app.register_blueprint(collection_bp)
    
    # 注册分析模块蓝图
    try:
        from gs2026.dashboard2.routes.analysis import analysis_bp
        app.register_blueprint(analysis_bp)
    except ImportError as e:
        print(f"Warning: Failed to load analysis routes: {e}")
    
    # 注册监控模块蓝图（原版）
    try:
        from gs2026.dashboard2.routes.monitor import monitor_bp
        app.register_blueprint(monitor_bp, url_prefix='/api/monitor')
    except ImportError as e:
        print(f"Warning: Failed to load monitor routes: {e}")
    
    # 注册股票-债券映射蓝图
    try:
        from gs2026.dashboard2.routes.stock_bond_mapping import bp as stock_bond_bp
        app.register_blueprint(stock_bond_bp)
    except ImportError as e:
        print(f"Warning: Failed to load stock_bond_mapping routes: {e}")
    
    # 注册红名单蓝图
    try:
        from gs2026.dashboard2.routes.red_list import bp as red_list_bp
        app.register_blueprint(red_list_bp)
        
        # 启动时初始化红名单缓存（先清理再更新）
        try:
            from gs2026.dashboard2.routes.red_list_cache import init_red_list_on_startup
            result = init_red_list_on_startup()
            print(f"红名单缓存初始化: {result}")
        except Exception as e:
            print(f"Warning: 红名单缓存初始化失败: {e}")
    except ImportError as e:
        print(f"Warning: Failed to load red_list routes: {e}")
    
    # 注册调度中心蓝图
    try:
        from gs2026.dashboard2.routes.scheduler import scheduler_bp
        app.register_blueprint(scheduler_bp)
        print("调度中心模块已加载")
    except ImportError as e:
        print(f"Warning: Failed to load scheduler routes: {e}")
    
    # 首页
    @app.route('/')
    def index():
        return render_template('index.html')
    
    # 数据采集
    @app.route('/collection')
    def collection():
        return render_template('collection.html')
    
    # 数据分析
    @app.route('/analysis')
    def analysis():
        return render_template('analysis.html')
    
    # 报表中心
    @app.route('/reports')
    def reports():
        return render_template('reports.html')
    
    # 数据监控
    @app.route('/monitor')
    def monitor():
        # 加载前端性能监控配置
        frontend_perf_config = {'enabled': False}
        try:
            import yaml
            config_path = Path(__file__).parent.parent.parent.parent / 'configs' / 'settings.yaml'
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    frontend_perf_config = config.get('frontend_perf', {'enabled': False})
        except Exception:
            pass
        
        return render_template('monitor.html', frontend_perf_config=frontend_perf_config)
    
    # 新闻中心
    @app.route('/news')
    def news():
        return render_template('news.html')
    
    # 调度中心
    @app.route('/scheduler')
    def scheduler():
        return render_template('scheduler.html')
    
    # 股债联动详情页（复用dashboard的chart.html模板）
    @app.route('/chart/<bond_code>/<stock_code>')
    def chart(bond_code, stock_code):
        """分时图页面 - 展示债券和正股的实时分时数据"""
        date = request.args.get('date', '')
        return render_template('chart.html', 
                               bond_code=bond_code, 
                               stock_code=stock_code,
                               date=date)
    
    # 注册数据库分析器诊断API（非侵入式）
    if PERF_MONITOR_AVAILABLE:
        @app.route('/diag/db', methods=['GET'])
        def diag_db():
            """获取数据库查询统计"""
            return DBProfiler().get_stats()
        
        @app.route('/diag/db/reset', methods=['POST'])
        def diag_db_reset():
            """重置数据库统计"""
            return DBProfiler().reset()
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
