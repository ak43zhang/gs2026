"""
慢查询/慢请求数据模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, Date, Integer, String, Text, SmallInteger, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class SlowRequest(Base):
    """慢请求记录"""
    __tablename__ = 'slow_requests'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    request_date = Column(Date, nullable=False)
    request_hour = Column(Integer, nullable=False)

    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False)
    endpoint = Column(String(200))

    duration_ms = Column(Integer, nullable=False)
    status_code = Column(SmallInteger)

    db_queries = Column(Integer, default=0)
    db_time_ms = Column(Integer, default=0)
    redis_queries = Column(Integer, default=0)
    redis_time_ms = Column(Integer, default=0)

    extra_info = Column(JSON)


class SlowQuery(Base):
    """慢查询记录"""
    __tablename__ = 'slow_queries'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    query_date = Column(Date, nullable=False)
    query_hour = Column(Integer, nullable=False)

    sql_statement = Column(Text, nullable=False)
    sql_hash = Column(String(64))
    sql_type = Column(String(20))

    duration_ms = Column(Integer, nullable=False)
    table_name = Column(String(100))
    parameters = Column(Text)

    extra_info = Column(JSON)


class SlowFrontendResource(Base):
    """前端慢资源加载记录"""
    __tablename__ = 'slow_frontend_resources'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    resource_date = Column(Date, nullable=False)
    resource_hour = Column(Integer, nullable=False)

    resource_type = Column(String(20), nullable=False)
    url = Column(String(1000), nullable=False)
    url_path = Column(String(500))

    duration_ms = Column(Integer, nullable=False)
    transfer_size = Column(BigInteger)

    page_url = Column(String(500))

    extra_info = Column(JSON)
