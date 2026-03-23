"""
GS2026 Dashboard - Web监控控制面板

独立的可视化监控模块，用于：
1. 实时监控数据展示（上攻排行、大盘数据等）
2. 控制面板（启动/停止采集、启动/停止AI分析）

启动命令: python -m gs2026.dashboard.app
访问地址: http://localhost:5000
"""

from flask import Flask, render_template, jsonify, request
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gs2026.dashboard.config import Config
from gs2026.dashboard.routes.monitor import monitor_bp
from gs2026.dashboard.routes.control import control_bp


def create_app():
    """创建Flask应用"""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static")
    )
    app.config.from_object(Config)
    
    # 注册蓝图
    app.register_blueprint(monitor_bp, url_prefix='/api/monitor')
    app.register_blueprint(control_bp, url_prefix='/api/control')
    
    @app.route('/')
    def index():
        """首页"""
        return render_template('index.html')
    
    @app.route('/monitor')
    def monitor_page():
        """监控页面"""
        return render_template('monitor.html')
    
    @app.route('/control')
    def control_page():
        """控制面板页面"""
        return render_template('control.html')
    
    return app


if __name__ == '__main__':
    app = create_app()
    print("=" * 50)
    print("GS2026 Dashboard 启动成功!")
    print("访问地址: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
