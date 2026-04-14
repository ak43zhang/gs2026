"""
Dashboard2 配置
"""

import os
from pathlib import Path
from gs2026.utils import config_util

class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-dashboard2'
    
    # 静态文件
    STATIC_FOLDER = 'static'
    TEMPLATE_FOLDER = 'templates'
    
    # API 配置
    API_BASE_URL = '/api'
    
    # 日志
    LOG_LEVEL = 'INFO'
    
    # Redis 配置（用于进程监控）
    REDIS_URL = 'redis://localhost:6379/0'
    
    # 进程监控配置
    PROCESS_MONITOR = {
        'enabled': True,
        'heartbeat_interval': 10,  # 心跳间隔（秒）
        'heartbeat_timeout': 30,   # 心跳超时（秒）
        'cleanup_days': 7         # 历史记录保留天数
    }
    
    # MySQL配置（从统一配置读取）
    _config = config_util.load_config()
    _mysql_config = _config.get('mysql', {})
    MYSQL_HOST = _mysql_config.get('host', '192.168.0.101')
    MYSQL_PORT = _mysql_config.get('port', 3306)
    MYSQL_USER = _mysql_config.get('user', 'root')
    MYSQL_PASSWORD = _mysql_config.get('password', '123456')
    MYSQL_DATABASE = _mysql_config.get('database', 'gs')
    
    # SQLAlchemy 数据库 URI
    MYSQL_URI = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8"
