"""
Dashboard2 配置
"""

import os
from pathlib import Path

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
