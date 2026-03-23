"""
Dashboard 配置
"""
import os
from pathlib import Path


class Config:
    """配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'gs2026-dashboard-secret-key'
    
    # MySQL配置（复用现有配置）
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or '192.168.0.101'
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT') or 3306)
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or '123456'
    MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE') or 'gs'
    
    # Redis配置
    REDIS_HOST = os.environ.get('REDIS_HOST') or 'localhost'
    REDIS_PORT = int(os.environ.get('REDIS_PORT') or 6379)
    REDIS_DB = int(os.environ.get('REDIS_DB') or 0)
    
    # 进程管理配置
    PROCESS_CHECK_INTERVAL = 5  # 秒
    
    # 数据刷新间隔（前端轮询）
    DATA_REFRESH_INTERVAL = 30000  # 毫秒（30秒）
