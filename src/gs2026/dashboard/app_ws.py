"""
GS2026 Dashboard with WebSocket - 带实时通知的监控面板

启动命令: python -m gs2026.dashboard.app_ws
访问地址: http://localhost:8080

特性：
- 原有 Dashboard 所有功能
- WebSocket 实时推送股债联动信号
- 浏览器语音播报
"""

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from gs2026.dashboard.config import Config
from gs2026.dashboard.routes.monitor import monitor_bp
from gs2026.dashboard.routes.control import control_bp
from gs2026.utils.websocket_notifier import init_socketio, get_socketio


def create_app():
    """创建Flask应用（带WebSocket）"""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static")
    )
    app.config.from_object(Config)
    app.config['SECRET_KEY'] = 'gs2026-secret-key'
    
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
        return render_template('monitor_ws.html')  # 使用带WebSocket的模板
    
    @app.route('/control')
    def control_page():
        """控制面板页面"""
        return render_template('control.html')
    
    @app.route('/chart/<bond_code>/<stock_code>')
    def chart_page(bond_code, stock_code):
        """分时图页面"""
        date = request.args.get('date', '')
        return render_template('chart.html', 
                               bond_code=bond_code, 
                               stock_code=stock_code,
                               date=date)
    
    # 初始化 WebSocket
    socketio = init_socketio(app)
    
    @socketio.on('connect')
    def handle_connect():
        """客户端连接"""
        print(f'[WebSocket] 客户端已连接: {request.sid}')
        emit('connected', {'status': 'ok', 'message': '已连接到GS2026'})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """客户端断开"""
        print(f'[WebSocket] 客户端已断开: {request.sid}')
    
    return app, socketio


if __name__ == '__main__':
    app, socketio = create_app()
    print("=" * 50)
    print("GS2026 Dashboard with WebSocket 启动成功!")
    print("=" * 50)
    print("访问地址:")
    print("  本机: http://127.0.0.1:5000")
    print("  局域网: http://0.0.0.0:5000")
    print("=" * 50)
    
    # 使用 5000 端口（标准端口）
    # allow_unsafe_werkzeug=True 用于禁用开发服务器警告（内网使用）
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
