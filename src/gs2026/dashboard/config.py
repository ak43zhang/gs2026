"""
Dashboard 配置 - 使用 config_util 统一读取 settings.yaml
"""
from pathlib import Path
from gs2026.utils import config_util


class Config:
    """Dashboard 配置类 - 从 settings.yaml 读取"""
    
    # 加载配置
    _config = config_util.load_config()
    
    # Dashboard 配置
    _dashboard_config = _config.get('dashboard', {})
    
    # Flask配置
    SECRET_KEY = _dashboard_config.get('secret_key', 'gs2026-dashboard-secret-key')
    
    # 服务器配置
    HOST = _dashboard_config.get('host', '0.0.0.0')
    PORT = _dashboard_config.get('port', 5000)
    DEBUG = _dashboard_config.get('debug', True)
    
    # MySQL配置（从统一配置读取）
    _mysql_config = _config.get('mysql', {})
    MYSQL_HOST = _mysql_config.get('host', '192.168.0.101')
    MYSQL_PORT = _mysql_config.get('port', 3306)
    MYSQL_USER = _mysql_config.get('user', 'root')
    MYSQL_PASSWORD = _mysql_config.get('password', '123456')
    MYSQL_DATABASE = _mysql_config.get('database', 'gs')
    
    # SQLAlchemy 数据库 URI
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8"
    
    # Redis配置
    _redis_config = _config.get('common', {}).get('redis', {})
    REDIS_HOST = _redis_config.get('host', 'localhost')
    REDIS_PORT = _redis_config.get('port', 6379)
    REDIS_DB = 0
    
    # 进程管理配置
    PROCESS_CHECK_INTERVAL = 5  # 秒
    
    # 数据刷新间隔（前端轮询）
    DATA_REFRESH_INTERVAL = _dashboard_config.get('refresh_interval', 30000)  # 毫秒
    
    # 是否允许查询 MySQL（Redis 无数据时回退）
    USE_MYSQL = _dashboard_config.get('use_mysql', False)
