"""
数据库配置
支持 gs 和 gs_platform 两个数据库
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

# 数据库配置
DATABASE_CONFIG = {
    'gs': {
        'host': '192.168.0.101',
        'port': 3306,
        'database': 'gs',
        'user': 'root',
        'password': '123456'
    },
    'gs_platform': {
        'host': '192.168.0.101',
        'port': 3306,
        'database': 'gs_platform',
        'user': 'root',
        'password': '123456'
    }
}


def get_db_url(db_name='gs'):
    """获取数据库连接URL"""
    config = DATABASE_CONFIG.get(db_name, DATABASE_CONFIG['gs'])
    return f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}?charset=utf8mb4"


# 创建引擎
engines = {}
sessions = {}

for db_name in DATABASE_CONFIG:
    engines[db_name] = create_engine(
        get_db_url(db_name),
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False
    )
    sessions[db_name] = scoped_session(sessionmaker(bind=engines[db_name]))


def get_session(db_name='gs'):
    """获取数据库会话"""
    return sessions.get(db_name, sessions['gs'])


def get_engine(db_name='gs'):
    """获取数据库引擎"""
    return engines.get(db_name, engines['gs'])


def init_platform_db():
    """初始化平台数据库（创建表）"""
    from .report_model import Base
    engine = get_engine('gs_platform')
    Base.metadata.create_all(engine)
    print("Platform database tables initialized")


if __name__ == '__main__':
    init_platform_db()
