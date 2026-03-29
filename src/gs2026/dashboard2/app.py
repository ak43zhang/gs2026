"""
Dashboard2 - 主应用
整合原版监控功能和新版采集功能
"""

from flask import Flask, render_template, redirect
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gs2026.dashboard2.config import Config

def create_app():
    """创建Flask应用"""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static")
    )
    app.config.from_object(Config)
    
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
        return render_template('monitor.html')
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
