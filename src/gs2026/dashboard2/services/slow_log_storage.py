"""
慢日志存储服务 - 实际的存储实现
"""
import hashlib
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import NullPool

from gs2026.dashboard.config import Config
from gs2026.dashboard2.models.slow_log import SlowRequest, SlowQuery, SlowFrontendResource, Base


class SlowLogStorage:
    """慢日志存储服务 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 从配置读取数据库连接
        config = Config()
        db_url = config.SQLALCHEMY_DATABASE_URI

        # 创建引擎
        self.engine = create_engine(
            db_url,
            poolclass=NullPool,
            pool_pre_ping=True,
            echo=False
        )

        # 创建会话工厂
        self.Session = scoped_session(sessionmaker(bind=self.engine))

        # 线程池用于异步写入
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="slow_log_")

        self._initialized = True

    def _parse_sql_type(self, sql: str) -> str:
        """解析SQL类型"""
        sql_upper = sql.strip().upper()
        if sql_upper.startswith('SELECT'):
            return 'SELECT'
        elif sql_upper.startswith('INSERT'):
            return 'INSERT'
        elif sql_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif sql_upper.startswith('DELETE'):
            return 'DELETE'
        return 'OTHER'

    def _parse_table_name(self, sql: str) -> Optional[str]:
        """简单解析主表名"""
        try:
            sql_upper = sql.upper()
            if 'FROM' in sql_upper:
                parts = sql_upper.split('FROM')[1].strip().split()
                if parts:
                    return parts[0].strip('`"[]')
            elif 'INTO' in sql_upper:
                parts = sql_upper.split('INTO')[1].strip().split()
                if parts:
                    return parts[0].strip('`"[]')
            elif 'UPDATE' in sql_upper:
                parts = sql_upper.split('UPDATE')[1].strip().split()
                if parts:
                    return parts[0].strip('`"[]')
        except:
            pass
        return None

    def _extract_url_path(self, url: str) -> str:
        """从URL提取路径部分"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.path
        except:
            return url[:200] if url else ''

    def save_slow_request_async(self, data: Dict[str, Any]):
        """异步保存慢请求记录"""
        try:
            self._executor.submit(self._save_slow_request_sync, data)
        except Exception as e:
            print(f"[SlowLogStorage] 提交异步慢请求任务失败: {e}")

    def _save_slow_request_sync(self, data: Dict[str, Any]) -> bool:
        """同步保存慢请求记录"""
        try:
            now = datetime.now()

            record = SlowRequest(
                created_at=now,
                request_date=now.date(),
                request_hour=now.hour,
                method=data.get('method', '')[:10],
                path=data.get('path', '')[:500],
                endpoint=data.get('endpoint', '')[:200] if data.get('endpoint') else None,
                duration_ms=int(data.get('duration_ms', 0)),
                status_code=data.get('status_code'),
                db_queries=data.get('db_queries', 0),
                db_time_ms=data.get('db_time_ms', 0),
                redis_queries=data.get('redis_queries', 0),
                redis_time_ms=data.get('redis_time_ms', 0),
                extra_info=data.get('extra_info')
            )

            session = self.Session()
            try:
                session.add(record)
                session.commit()
                return True
            finally:
                session.close()

        except Exception as e:
            print(f"[SlowLogStorage] 保存慢请求失败: {e}")
            return False

    def save_slow_query_async(self, data: Dict[str, Any]):
        """异步保存慢查询记录"""
        try:
            self._executor.submit(self._save_slow_query_sync, data)
        except Exception as e:
            print(f"[SlowLogStorage] 提交异步慢查询任务失败: {e}")

    def _save_slow_query_sync(self, data: Dict[str, Any]) -> bool:
        """同步保存慢查询记录"""
        try:
            now = datetime.now()
            sql = data.get('sql_statement', '')

            # 计算SQL哈希
            sql_hash = hashlib.md5(sql.encode()).hexdigest()

            # 解析SQL类型
            sql_type = self._parse_sql_type(sql)

            # 解析表名
            table_name = self._parse_table_name(sql)

            record = SlowQuery(
                created_at=now,
                query_date=now.date(),
                query_hour=now.hour,
                sql_statement=sql[:500],
                sql_hash=sql_hash,
                sql_type=sql_type,
                duration_ms=int(data.get('duration_ms', 0)),
                table_name=table_name[:100] if table_name else None,
                parameters=str(data.get('parameters', ''))[:200] if data.get('parameters') else None,
                extra_info=data.get('extra_info')
            )

            session = self.Session()
            try:
                session.add(record)
                session.commit()
                return True
            finally:
                session.close()

        except Exception as e:
            print(f"[SlowLogStorage] 保存慢查询失败: {e}")
            return False

    def save_slow_frontend_resource_async(self, data: Dict[str, Any]):
        """异步保存前端慢资源记录"""
        try:
            self._executor.submit(self._save_slow_frontend_resource_sync, data)
        except Exception as e:
            print(f"[SlowLogStorage] 提交异步前端慢资源任务失败: {e}")

    def _save_slow_frontend_resource_sync(self, data: Dict[str, Any]) -> bool:
        """同步保存前端慢资源记录"""
        try:
            now = datetime.now()
            url = data.get('url', '')

            # 提取URL路径
            url_path = self._extract_url_path(url)

            record = SlowFrontendResource(
                created_at=now,
                resource_date=now.date(),
                resource_hour=now.hour,
                resource_type=data.get('resource_type', 'other')[:20],
                url=url[:1000],
                url_path=url_path[:500] if url_path else None,
                duration_ms=int(data.get('duration_ms', 0)),
                transfer_size=data.get('transfer_size'),
                page_url=data.get('page_url', '')[:500] if data.get('page_url') else None,
                extra_info=data.get('extra_info')
            )

            session = self.Session()
            try:
                session.add(record)
                session.commit()
                return True
            finally:
                session.close()

        except Exception as e:
            print(f"[SlowLogStorage] 保存前端慢资源失败: {e}")
            return False

    def get_stats(self, date: str = None) -> Dict[str, Any]:
        """获取统计信息"""
        session = self.Session()

        try:
            # 慢请求统计
            req_query = session.query(
                func.count(SlowRequest.id).label('total'),
                func.avg(SlowRequest.duration_ms).label('avg_duration'),
                func.max(SlowRequest.duration_ms).label('max_duration')
            )

            if date:
                req_query = req_query.filter(SlowRequest.request_date == date)

            req_stats = req_query.first()

            # 慢查询统计
            query_query = session.query(
                func.count(SlowQuery.id).label('total'),
                func.avg(SlowQuery.duration_ms).label('avg_duration'),
                func.max(SlowQuery.duration_ms).label('max_duration')
            )

            if date:
                query_query = query_query.filter(SlowQuery.query_date == date)

            query_stats = query_query.first()

            # 前端慢资源统计
            fe_query = session.query(
                func.count(SlowFrontendResource.id).label('total'),
                func.avg(SlowFrontendResource.duration_ms).label('avg_duration'),
                func.max(SlowFrontendResource.duration_ms).label('max_duration')
            )

            if date:
                fe_query = fe_query.filter(SlowFrontendResource.resource_date == date)

            fe_stats = fe_query.first()

            return {
                'slow_requests': {
                    'total': req_stats.total or 0,
                    'avg_duration': round(req_stats.avg_duration or 0, 2),
                    'max_duration': req_stats.max_duration or 0
                },
                'slow_queries': {
                    'total': query_stats.total or 0,
                    'avg_duration': round(query_stats.avg_duration or 0, 2),
                    'max_duration': query_stats.max_duration or 0
                },
                'slow_frontend': {
                    'total': fe_stats.total or 0,
                    'avg_duration': round(fe_stats.avg_duration or 0, 2),
                    'max_duration': fe_stats.max_duration or 0
                }
            }

        except Exception as e:
            print(f"[SlowLogStorage] 获取统计信息失败: {e}")
            return {
                'slow_requests': {'total': 0, 'avg_duration': 0, 'max_duration': 0},
                'slow_queries': {'total': 0, 'avg_duration': 0, 'max_duration': 0},
                'slow_frontend': {'total': 0, 'avg_duration': 0, 'max_duration': 0}
            }
        finally:
            session.close()

    def get_slow_requests(self, date: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取慢请求列表"""
        session = self.Session()

        try:
            query = session.query(SlowRequest)
            if date:
                query = query.filter(SlowRequest.request_date == date)
            query = query.order_by(SlowRequest.created_at.desc()).limit(limit)

            return [
                {
                    'id': r.id,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'method': r.method,
                    'path': r.path,
                    'endpoint': r.endpoint,
                    'duration_ms': r.duration_ms,
                    'status_code': r.status_code,
                    'db_queries': r.db_queries,
                    'db_time_ms': r.db_time_ms,
                    'redis_queries': r.redis_queries,
                    'redis_time_ms': r.redis_time_ms
                }
                for r in query.all()
            ]
        except Exception as e:
            print(f"[SlowLogStorage] 获取慢请求列表失败: {e}")
            return []
        finally:
            session.close()

    def get_slow_queries(self, date: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取慢查询列表"""
        session = self.Session()

        try:
            query = session.query(SlowQuery)
            if date:
                query = query.filter(SlowQuery.query_date == date)
            query = query.order_by(SlowQuery.created_at.desc()).limit(limit)

            return [
                {
                    'id': q.id,
                    'created_at': q.created_at.isoformat() if q.created_at else None,
                    'sql_statement': q.sql_statement,
                    'sql_hash': q.sql_hash,
                    'sql_type': q.sql_type,
                    'duration_ms': q.duration_ms,
                    'table_name': q.table_name,
                    'parameters': q.parameters
                }
                for q in query.all()
            ]
        except Exception as e:
            print(f"[SlowLogStorage] 获取慢查询列表失败: {e}")
            return []
        finally:
            session.close()

    def get_slow_frontend_resources(self, date: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取前端慢资源列表"""
        session = self.Session()

        try:
            query = session.query(SlowFrontendResource)
            if date:
                query = query.filter(SlowFrontendResource.resource_date == date)
            query = query.order_by(SlowFrontendResource.created_at.desc()).limit(limit)

            return [
                {
                    'id': r.id,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'resource_type': r.resource_type,
                    'url': r.url,
                    'url_path': r.url_path,
                    'duration_ms': r.duration_ms,
                    'transfer_size': r.transfer_size,
                    'page_url': r.page_url
                }
                for r in query.all()
            ]
        except Exception as e:
            print(f"[SlowLogStorage] 获取前端慢资源列表失败: {e}")
            return []
        finally:
            session.close()

    def get_hotspot_analysis(self, days: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """获取热点分析"""
        session = self.Session()

        try:
            from_date = (datetime.now() - timedelta(days=days)).date()

            # 热点API
            api_hotspot = session.query(
                SlowRequest.path,
                func.count(SlowRequest.id).label('count'),
                func.avg(SlowRequest.duration_ms).label('avg_duration'),
                func.max(SlowRequest.duration_ms).label('max_duration')
            ).filter(
                SlowRequest.request_date >= from_date
            ).group_by(
                SlowRequest.path
            ).order_by(
                func.count(SlowRequest.id).desc()
            ).limit(10).all()

            # 热点SQL
            sql_hotspot = session.query(
                SlowQuery.sql_hash,
                SlowQuery.sql_statement,
                func.count(SlowQuery.id).label('count'),
                func.avg(SlowQuery.duration_ms).label('avg_duration'),
                func.max(SlowQuery.duration_ms).label('max_duration')
            ).filter(
                SlowQuery.query_date >= from_date
            ).group_by(
                SlowQuery.sql_hash,
                SlowQuery.sql_statement
            ).order_by(
                func.count(SlowQuery.id).desc()
            ).limit(10).all()

            # 热点前端资源
            fe_hotspot = session.query(
                SlowFrontendResource.url_path,
                func.count(SlowFrontendResource.id).label('count'),
                func.avg(SlowFrontendResource.duration_ms).label('avg_duration'),
                func.max(SlowFrontendResource.duration_ms).label('max_duration')
            ).filter(
                SlowFrontendResource.resource_date >= from_date
            ).group_by(
                SlowFrontendResource.url_path
            ).order_by(
                func.count(SlowFrontendResource.id).desc()
            ).limit(10).all()

            return {
                'api': [
                    {
                        'path': item.path,
                        'count': item.count,
                        'avg_duration': round(item.avg_duration, 2),
                        'max_duration': item.max_duration
                    }
                    for item in api_hotspot
                ],
                'sql': [
                    {
                        'sql_hash': item.sql_hash,
                        'sql_statement': item.sql_statement[:100] + '...' if len(item.sql_statement) > 100 else item.sql_statement,
                        'count': item.count,
                        'avg_duration': round(item.avg_duration, 2),
                        'max_duration': item.max_duration
                    }
                    for item in sql_hotspot
                ],
                'frontend': [
                    {
                        'url_path': item.url_path,
                        'count': item.count,
                        'avg_duration': round(item.avg_duration, 2),
                        'max_duration': item.max_duration
                    }
                    for item in fe_hotspot
                ]
            }

        except Exception as e:
            print(f"[SlowLogStorage] 获取热点分析失败: {e}")
            return {'api': [], 'sql': [], 'frontend': []}
        finally:
            session.close()
