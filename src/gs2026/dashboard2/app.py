"""
Dashboard2 - 应用入口
整合原版监控功能和新版采集功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 配置日志（必须在导入其他模块前）
from gs2026.dashboard2.core.logger import LoggerManager
logger = LoggerManager.setup(app_name='dashboard2', log_dir='logs')

# 创建应用
from gs2026.dashboard2.core.app_factory import create_app
app = create_app()

if __name__ == '__main__':
    import logging
    logging.getLogger('waitress.queue').setLevel(logging.ERROR)
    from waitress import serve
    serve(app, host='0.0.0.0', port=8080)
