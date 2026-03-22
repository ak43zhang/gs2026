"""
分布式账号池管理器 - 多进程安全版
解决单例模式在多进程环境下失效的问题
支持多服务类型账号管理
"""
import atexit
import logging
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    create_engine, text
)
from sqlalchemy.engine import Result
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, scoped_session

from gs2026.utils.config_util import get_config

logger = logging.getLogger(__name__)


class AccountPool:
    """
    分布式账号池 - 多进程安全版

    核心改进：
    1. 进程内连接池优化：控制每个进程的最大连接数
    2. 分布式锁机制：使用数据库行锁确保跨进程安全
    3. 连接池监控：实时监控连接使用情况
    4. 智能清理：避免多个进程同时清理造成资源竞争
    5. 多服务支持：支持管理不同服务的账号
    """

    # 类变量：跟踪所有实例的数据库URL
    _database_instances = {}
    _lock = threading.Lock()

    def __init__(self, database_url: str, default_lease_time: int = 300,
                 pool_size: int = 2, max_overflow: int = 3,
                 service_type: str = "default"):
        """
        初始化账号池

        Args:
            database_url: MySQL数据库连接URL
            default_lease_time: 默认租用时间（秒）
            pool_size: 连接池大小（每个进程）
            max_overflow: 最大溢出连接数（每个进程）
            service_type: 服务类型，如deepseek、gemini等
        """
        # 生成进程唯一标识
        self.process_id = f"{socket.gethostname()}_{uuid.uuid4().hex[:8]}"

        # 服务类型
        self.service_type = service_type

        # 使用更小的连接池配置，控制每个进程的连接数
        self.engine = create_engine(
            database_url,
            pool_size=pool_size,           # 每个进程的基础连接数
            max_overflow=max_overflow,      # 每个进程的最大溢出连接数
            pool_recycle=650,              # 30分钟回收连接
            pool_pre_ping=True,             # 连接前检查
            pool_timeout=30,                # 获取连接超时
            echo=False,
            isolation_level="READ COMMITTED",
            connect_args={
                'connect_timeout': 10,      # 连接超时10秒
            }
        )

        # 注册连接池清理
        atexit.register(self._cleanup_pool)

        # 创建线程安全的session工厂
        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )

        # 使用scoped_session确保线程安全
        self.ScopedSession = scoped_session(self.session_factory)

        # 客户端标识（进程+线程）
        self.client_id = f"{self.process_id}_thread_{threading.current_thread().ident}"

        # 配置参数
        self.default_lease_time = default_lease_time
        self.max_wait_time = 30
        self.retry_interval = 0.5

        # 清理控制：避免多个进程同时清理
        self.last_cleanup_time = 0
        self.cleanup_interval = 30  # 30秒

        # 线程局部存储
        self._thread_local = threading.local()

        # 统计信息
        self.stats = {
            'connection_attempts': 0,
            'successful_connections': 0,
            'failed_connections': 0,
            'account_acquires': 0,
            'account_releases': 0,
            'last_error': None
        }

        # 注册到全局实例跟踪器
        with AccountPool._lock:
            if database_url not in AccountPool._database_instances:
                AccountPool._database_instances[database_url] = []
            AccountPool._database_instances[database_url].append(self)

        # 确保表存在
        self._ensure_table_exists()

        logger.info(f"账号池初始化完成 - 进程ID: {self.process_id}, "
                   f"服务类型: {service_type}, "
                   f"连接池配置: pool_size={pool_size}, max_overflow={max_overflow}")

    def _ensure_table_exists(self):
        """确保 accounts 表存在"""
        try:
            session = self._get_session()
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    service_type VARCHAR(50) NOT NULL DEFAULT 'default',
                    is_locked TINYINT(1) NOT NULL DEFAULT 0,
                    locked_by VARCHAR(255),
                    locked_at TIMESTAMP NULL,
                    use_count INT NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    last_used TIMESTAMP NULL,
                    UNIQUE KEY uk_username_service (username, service_type),
                    INDEX idx_service_type (service_type),
                    INDEX idx_is_locked (is_locked)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            session.commit()
            logger.info("accounts 表已创建或已存在")
        except Exception as e:
            logger.warning(f"创建表失败（可能已存在）: {e}")
            try:
                session.rollback()
            except:
                pass

    def _cleanup_pool(self):
        """清理连接池"""
        try:
            self.engine.dispose()
            logger.info(f"连接池已清理 - 进程ID: {self.process_id}")
        except Exception as e:
            logger.error(f"清理连接池失败: {e}")

    def _get_session(self, new: bool = False):
        """
        获取数据库会话

        Args:
            new: 是否强制创建新的session
        """
        if not new and hasattr(self._thread_local, "session"):
            try:
                # 测试session是否仍然有效
                self._thread_local.session.execute(text("SELECT 1"))
                return self._thread_local.session
            except Exception:
                try:
                    self._thread_local.session.close()
                except:
                    pass
                delattr(self._thread_local, "session")

        # 创建新的session
        session = self.ScopedSession()
        self._thread_local.session = session
        return session

    def _release_session(self, commit: bool = False):
        """释放当前线程的session"""
        if hasattr(self._thread_local, "session"):
            try:
                if commit:
                    self._thread_local.session.commit()
                else:
                    self._thread_local.session.rollback()
            except Exception as e:
                logger.error(f"会话提交/回滚失败: {e}")
                try:
                    self._thread_local.session.rollback()
                except:
                    pass

    def _check_and_cleanup_expired_locks(self, service_type: Optional[str] = None):
        """
        检查并清理过期锁
        使用分布式协调，避免多个进程同时清理

        Args:
            service_type: 服务类型，None表示清理所有服务
        """
        current_time = time.time()

        # 检查是否需要清理（避免频繁清理）
        if current_time - self.last_cleanup_time < self.cleanup_interval:
            return

        session = self._get_session()
        try:
            # 使用数据库的分布式锁机制
            # 尝试获取一个清理锁，避免多个进程同时清理
            # 注意：GET_LOCK是MySQL函数，需要通过SELECT调用
            lock_name = f"account_pool_cleanup_{service_type or 'all'}"
            lock_result = session.execute(
                text(f"""
                    SELECT GET_LOCK(:lock_name, 1)
                """),
                {"lock_name": lock_name}
            ).scalar()

            if lock_result == 1:  # 成功获取锁
                try:
                    now = datetime.now()

                    # 构建SQL查询条件
                    sql = """
                        UPDATE accounts 
                        SET is_locked = 0, 
                            locked_by = NULL, 
                            lock_time = NULL, 
                            lock_expiry = NULL,
                            version = version + 1,
                            updated_at = NOW()
                        WHERE is_locked = 1 
                          AND lock_expiry < :now
                    """
                    params = {"now": now}

                    # 如果指定了服务类型，添加条件
                    if service_type:
                        sql += " AND service_type = :service_type"
                        params["service_type"] = service_type
                    else:
                        # 如果没有指定服务类型，使用实例的服务类型
                        sql += " AND service_type = :service_type"
                        params["service_type"] = self.service_type

                    # 清理过期锁
                    result:Result = session.execute(
                        text(sql),
                        params
                    )

                    if result.rowcount > 0:
                        session.commit()
                        logger.info(f"清理了 {result.rowcount} 个过期的账号锁 - 进程: {self.process_id}, 服务: {service_type or self.service_type}")

                    self.last_cleanup_time = current_time

                finally:
                    # 释放清理锁
                    session.execute(
                        text(f"SELECT RELEASE_LOCK(:lock_name)"),
                        {"lock_name": lock_name}
                    )
            else:
                # 其他进程正在清理，跳过
                logger.debug(f"其他进程正在清理服务{service_type or self.service_type}，跳过本次清理")

        except Exception as e:
            session.rollback()
            logger.error(f"清理过期锁失败: {e}")
        finally:
            self._release_session()

    def add_account(self, username: str, password: str, service_type: Optional[str] = None, **kwargs) -> bool:
        """
        添加新账号到池中

        Args:
            username: 用户名
            password: 密码
            service_type: 服务类型，如deepseek、gemini等。如果为None，使用实例的服务类型
            **kwargs: 其他参数
        """
        session = self._get_session()
        try:
            # 确定服务类型
            target_service_type = service_type or self.service_type

            # 检查账号是否已存在
            result = session.execute(
                text("""
                    SELECT 1 FROM accounts 
                    WHERE username = :username 
                      AND service_type = :service_type
                    FOR UPDATE
                """),
                {"username": username, "service_type": target_service_type}
            ).fetchone()

            if result:
                logger.warning(f"账号已存在: {username}, 服务类型: {target_service_type}")
                return False

            # 插入新账号
            session.execute(
                text("""
                    INSERT INTO accounts 
                    (username, password, service_type, is_locked, use_count, 
                     created_at, updated_at, last_used)
                    VALUES 
                    (:username, :password, :service_type, 0, 0, 
                     NOW(), NOW(), NULL)
                """),
                {
                    "username": username,
                    "password": password,
                    "service_type": target_service_type,
                    **kwargs
                }
            )

            session.commit()
            logger.info(f"成功添加账号: {username}, 服务类型: {target_service_type}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"添加账号失败: {e}")
            return False
        finally:
            self._release_session()

    def acquire_account(self, service_type: Optional[str] = None, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        获取一个可用账号 - 支持多进程并发

        Args:
            service_type: 服务类型，如deepseek、gemini等。如果为None，使用实例的服务类型
            timeout: 超时时间
        """
        target_service_type = service_type or self.service_type
        timeout = timeout or self.max_wait_time
        start_time = time.time()
        attempt = 0

        # 先检查并清理过期锁
        self._check_and_cleanup_expired_locks(target_service_type)

        while time.time() - start_time < timeout:
            attempt += 1
            self.stats['account_acquires'] += 1

            account_info = self._try_acquire_account(target_service_type)

            if account_info:
                self.stats['successful_connections'] += 1
                logger.debug(f"成功获取账号: {account_info['username']} (服务: {target_service_type}, 尝试次数: {attempt})")
                return account_info

            # 等待后重试
            wait_time = min(self.retry_interval * (1.5 ** (attempt - 1)), 2.0)
            if time.time() - start_time + wait_time > timeout:
                break

            time.sleep(wait_time)

        self.stats['failed_connections'] += 1
        logger.warning(f"获取账号超时 (服务: {target_service_type}, 超时: {timeout}秒), 尝试次数: {attempt}")
        return None

    def _try_acquire_account(self, service_type: str) -> Optional[Dict[str, Any]]:
        """
        尝试获取账号（单次尝试）
        使用FOR UPDATE NOWAIT避免锁等待，提高并发性能

        Args:
            service_type: 服务类型
        """
        session = self._get_session()
        try:
            now = datetime.now()

            # 使用FOR UPDATE SKIP LOCKED快速获取锁，避免等待
            # 如果获取失败立即返回，而不是等待
            if 'mysql' in str(self.engine.url).lower():
                # MySQL支持SKIP LOCKED
                query = """
                    SELECT id, username, password, service_type
                    FROM accounts 
                    WHERE service_type = :service_type
                      AND (is_locked = 0 
                       OR (is_locked = 1 AND lock_expiry < :now))
                    ORDER BY 
                        CASE WHEN last_used IS NULL THEN 0 ELSE 1 END,
                        use_count ASC,
                        last_used ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """
            else:
                # PostgreSQL或其他数据库
                query = """
                    SELECT id, username, password, service_type
                    FROM accounts 
                    WHERE service_type = :service_type
                      AND (is_locked = 0 
                       OR (is_locked = 1 AND lock_expiry < :now))
                    ORDER BY 
                        CASE WHEN last_used IS NULL THEN 0 ELSE 1 END,
                        use_count ASC,
                        last_used ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """

            try:
                result = session.execute(
                    text(query),
                    {"now": now, "service_type": service_type}
                ).fetchone()
            except OperationalError as e:
                # 锁获取失败，立即返回None
                if 'Lock wait timeout' in str(e) or 'SKIP LOCKED' in str(e):
                    return None
                raise

            if not result:
                return None

            account_id, username, password, account_service_type = result

            # 更新账号状态
            lease_expiry = now + timedelta(seconds=self.default_lease_time)

            session.execute(
                text("""
                    UPDATE accounts 
                    SET is_locked = 1,
                        locked_by = :client_id,
                        lock_time = :now,
                        lock_expiry = :expiry,
                        use_count = use_count + 1,
                        last_used = :now,
                        updated_at = :now,
                        version = version + 1
                    WHERE id = :account_id
                """),
                {
                    "client_id": self.client_id,
                    "now": now,
                    "expiry": lease_expiry,
                    "account_id": account_id
                }
            )

            session.commit()

            return {
                'id': account_id,
                'username': username,
                'password': password,
                'service_type': account_service_type,
                'lease_expiry': lease_expiry.isoformat(),
                'client_id': self.client_id,
                'process_id': self.process_id
            }

        except Exception as e:
            session.rollback()
            logger.error(f"获取账号失败 (服务: {service_type}): {e}")
            return None
        finally:
            self._release_session()

    def release_account(self, account_id: int, force: bool = False) -> bool:
        """
        释放账号
        """
        session = self._get_session()
        try:
            # 使用行锁确保一致性
            result = session.execute(
                text("""
                    SELECT locked_by, is_locked, service_type 
                    FROM accounts 
                    WHERE id = :id 
                    FOR UPDATE
                """),
                {"id": account_id}
            ).fetchone()

            if not result:
                logger.warning(f"账号不存在: {account_id}")
                return False

            locked_by, is_locked, service_type = result

            # 检查是否有权释放
            if is_locked:
                # 检查是否由当前客户端锁定
                if locked_by and locked_by.startswith(self.process_id):
                    # 同一进程内的任何线程都可以释放
                    pass
                elif not force:
                    logger.warning(
                        f"账号 {account_id} (服务: {service_type}) 被其他进程锁定 "
                        f"(锁定者: {locked_by}, 当前进程: {self.process_id})"
                    )
                    return False

            # 释放账号
            session.execute(
                text("""
                    UPDATE accounts 
                    SET is_locked = 0,
                        locked_by = NULL,
                        lock_time = NULL,
                        lock_expiry = NULL,
                        updated_at = NOW(),
                        version = version + 1
                    WHERE id = :account_id
                """),
                {"account_id": account_id}
            )

            session.commit()
            self.stats['account_releases'] += 1
            logger.debug(f"成功释放账号 (ID: {account_id}, 服务: {service_type})")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"释放账号失败: {e}")
            return False
        finally:
            self._release_session()

    def renew_lease(self, account_id: int, extra_seconds: int = 300) -> bool:
        """
        续租账号
        """
        session = self._get_session()
        try:
            # 检查账号状态并锁定
            result = session.execute(
                text("""
                    SELECT locked_by, service_type 
                    FROM accounts 
                    WHERE id = :id AND is_locked = 1
                    FOR UPDATE
                """),
                {"id": account_id}
            ).fetchone()

            if not result or not result[0] or not result[0].startswith(self.process_id):
                logger.warning(f"无法续租账号: {account_id} (非本进程锁定)")
                return False

            service_type = result[1]

            # 续租
            new_expiry = datetime.now() + timedelta(seconds=extra_seconds)

            session.execute(
                text("""
                    UPDATE accounts 
                    SET lock_expiry = :expiry,
                        updated_at = NOW(),
                        version = version + 1
                    WHERE id = :account_id
                """),
                {
                    "expiry": new_expiry,
                    "account_id": account_id
                }
            )

            session.commit()
            logger.info(f"账号 {account_id} (服务: {service_type}) 续租成功，新过期时间: {new_expiry}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"续租失败: {e}")
            return False
        finally:
            self._release_session()

    def get_account_status(self, service_type: Optional[str] = None) -> Dict[str, Any]:
        """
        获取账号池状态统计

        Args:
            service_type: 服务类型，None表示获取所有服务的统计
        """
        session = self._get_session()
        try:
            now = datetime.now()

            # 构建SQL查询条件
            sql = """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_locked = 0 THEN 1 ELSE 0 END) as available_now,
                    SUM(CASE WHEN is_locked = 1 AND lock_expiry < :now THEN 1 ELSE 0 END) as expired_locked,
                    SUM(CASE WHEN is_locked = 1 AND locked_by LIKE :process_prefix THEN 1 ELSE 0 END) as my_locked,
                    SUM(use_count) as total_uses,
                    AVG(use_count) as avg_uses
                FROM accounts
            """

            params = {
                "now": now,
                "process_prefix": f"{self.process_id}%"
            }

            # 如果指定了服务类型，添加条件
            if service_type:
                sql += " WHERE service_type = :service_type"
                params["service_type"] = service_type
            else:
                # 如果没有指定服务类型，使用实例的服务类型
                sql += " WHERE service_type = :service_type"
                params["service_type"] = self.service_type

            # 获取统计信息
            result = session.execute(text(sql), params).fetchone()

            total, available_now, expired_locked, my_locked, total_uses, avg_uses = result

            # 获取连接池状态
            pool_status = self.engine.pool.status()

            return {
                'service_type': service_type or self.service_type,
                'total_accounts': total or 0,
                'available_accounts': (available_now or 0) + (expired_locked or 0),
                'locked_by_me': my_locked or 0,
                'total_uses': total_uses or 0,
                'avg_uses': float(avg_uses or 0),
                'process_id': self.process_id,
                'client_id': self.client_id,
                'pool_status': {
                    'size': getattr(pool_status, 'size', 0),
                    'checkedin': getattr(pool_status, 'checkedin', 0),
                    'checkedout': getattr(pool_status, 'checkedout', 0),
                    'overflow': getattr(pool_status, 'overflow', 0),
                },
                'stats': self.stats.copy()
            }

        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return {}
        finally:
            self._release_session()

    def get_all_service_types(self) -> List[str]:
        """
        获取所有服务类型列表
        """
        session = self._get_session()
        try:
            result = session.execute(
                text("""
                    SELECT DISTINCT service_type 
                    FROM accounts 
                    ORDER BY service_type
                """)
            ).fetchall()

            return [row[0] for row in result] if result else []
        except Exception as e:
            logger.error(f"获取服务类型列表失败: {e}")
            return []
        finally:
            self._release_session()

    def get_service_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有服务类型的统计信息
        """
        session = self._get_session()
        try:
            now = datetime.now()

            # 查询每个服务类型的统计信息
            result = session.execute(
                text("""
                    SELECT 
                        service_type,
                        COUNT(*) as total,
                        SUM(CASE WHEN is_locked = 0 THEN 1 ELSE 0 END) as available,
                        SUM(CASE WHEN is_locked = 1 AND lock_expiry < :now THEN 1 ELSE 0 END) as expired,
                        SUM(CASE WHEN is_locked = 1 AND locked_by LIKE :process_prefix THEN 1 ELSE 0 END) as my_locked,
                        SUM(use_count) as total_uses,
                        AVG(use_count) as avg_uses
                    FROM accounts
                    GROUP BY service_type
                    ORDER BY service_type
                """),
                {
                    "now": now,
                    "process_prefix": f"{self.process_id}%"
                }
            ).fetchall()

            stats = {}
            for row in result:
                service_type = row[0]
                stats[service_type] = {
                    'total_accounts': row[1] or 0,
                    'available_accounts': (row[2] or 0) + (row[3] or 0),
                    'expired_locks': row[3] or 0,
                    'locked_by_me': row[4] or 0,
                    'total_uses': row[5] or 0,
                    'avg_uses': float(row[6] or 0)
                }

            return stats
        except Exception as e:
            logger.error(f"获取服务统计失败: {e}")
            return {}
        finally:
            self._release_session()

    @contextmanager
    def get_account_context(self, service_type: Optional[str] = None, timeout: Optional[float] = None):
        """
        使用上下文管理器获取账号

        Args:
            service_type: 服务类型，如deepseek、gemini等。如果为None，使用实例的服务类型
            timeout: 超时时间
        """
        account_info = None
        account_id = None

        try:
            account_info = self.acquire_account(service_type, timeout)
            if account_info:
                account_id = account_info['id']
            yield account_info
        except Exception as e:
            logger.error(f"使用账号时发生错误: {e}")
            raise
        finally:
            if account_id:
                try:
                    self.release_account(account_id)
                except Exception as e:
                    logger.error(f"释放账号失败: {e}")
            # 清理当前线程的session
            if hasattr(self._thread_local, "session"):
                try:
                    self._thread_local.session.close()
                except:
                    pass
                self._thread_local.session = None
                self.ScopedSession.remove()

    def get_database_instances_info(self) -> Dict[str, Any]:
        """
        获取所有使用相同数据库的实例信息
        """
        with AccountPool._lock:
            instances = AccountPool._database_instances.get(str(self.engine.url), [])

            return {
                'database_url': str(self.engine.url),
                'total_instances': len(instances),
                'instance_ids': [instance.process_id for instance in instances],
                'instance_service_types': [instance.service_type for instance in instances],
                'current_instance': self.process_id,
                'current_service_type': self.service_type
            }

    def shutdown(self):
        """关闭账号池"""
        # 清理当前线程的session
        if hasattr(self._thread_local, "session"):
            try:
                self._thread_local.session.close()
            except:
                pass

        # 从全局实例跟踪器中移除
        with AccountPool._lock:
            url = str(self.engine.url)
            if url in AccountPool._database_instances:
                AccountPool._database_instances[url] = [
                    inst for inst in AccountPool._database_instances[url]
                    if inst.process_id != self.process_id
                ]
                if not AccountPool._database_instances[url]:
                    del AccountPool._database_instances[url]

        # 清理连接池
        self._cleanup_pool()
        logger.info(f"账号池已关闭 - 进程ID: {self.process_id}, 服务类型: {self.service_type}")


class DistributedAccountPool:
    """
    分布式账号池的高级封装
    提供更简单的API和更好的错误处理
    支持多服务类型账号管理
    """

    def __init__(self, database_url: str, service_type: str = "default", **kwargs):
        """
        初始化分布式账号池

        Args:
            database_url: 数据库连接URL
            service_type: 服务类型，如deepseek、gemini等
            **kwargs: 传递给AccountPool的额外参数
        """
        self.pool = AccountPool(database_url, service_type=service_type, **kwargs)
        self.database_url = database_url
        self.service_type = service_type

        # 验证数据库连接
        self._validate_connection()

    def _validate_connection(self):
        """验证数据库连接"""
        try:
            status = self.pool.get_account_status()
            logger.info(f"数据库连接验证成功 - 服务类型: {self.service_type}, 当前账号数: {status.get('total_accounts', 0)}")
            return True
        except Exception as e:
            logger.error(f"数据库连接验证失败: {e}")
            raise

    def get_account(self, service_type: Optional[str] = None, timeout: float = 30) -> Optional[Dict[str, Any]]:
        """
        获取一个账号（简化API）

        Args:
            service_type: 服务类型，如deepseek、gemini等。如果为None，使用实例的服务类型
            timeout: 超时时间
        """
        return self.pool.acquire_account(service_type, timeout)

    def release(self, account_info: Dict[str, Any]) -> bool:
        """
        释放账号（简化API）
        """
        if not account_info or 'id' not in account_info:
            return False
        return self.pool.release_account(account_info['id'])

    def add_account(self, username: str, password: str, service_type: Optional[str] = None, **kwargs) -> bool:
        """
        添加账号（简化API）

        Args:
            username: 用户名
            password: 密码
            service_type: 服务类型，如deepseek、gemini等。如果为None，使用实例的服务类型
            **kwargs: 其他参数
        """
        return self.pool.add_account(username, password, service_type, **kwargs)

    @contextmanager
    def account(self, service_type: Optional[str] = None, timeout: float = 30):
        """
        上下文管理器获取账号（简化API）

        Args:
            service_type: 服务类型，如deepseek、gemini等。如果为None，使用实例的服务类型
            timeout: 超时时间
        """
        account_info = None
        try:
            account_info = self.get_account(service_type, timeout)
            yield account_info
        finally:
            if account_info:
                self.release(account_info)

    def status(self, service_type: Optional[str] = None) -> Dict[str, Any]:
        """获取状态信息"""
        return self.pool.get_account_status(service_type)

    def get_all_services(self) -> Dict[str, Dict[str, Any]]:
        """获取所有服务的统计信息"""
        return self.pool.get_service_stats()

    def close(self):
        """关闭连接池"""
        self.pool.shutdown()


# 使用示例
if __name__ == "__main__":
    url = get_config("common.url")
    print(url)
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 示例1: 创建deepseek服务的账号池
    deepseek_pool = DistributedAccountPool(
        database_url=url,
        service_type="deepseek",
        default_lease_time=300,
        pool_size=2,
        max_overflow=3
    )

    # 示例2: 创建gemini服务的账号池
    gemini_pool = DistributedAccountPool(
        database_url=url,
        service_type="gemini",
        default_lease_time=300,
        pool_size=2,
        max_overflow=3
    )

    try:
        # 示例3: 添加deepseek账号
        print("添加deepseek账号...")
        deepseek_pool.add_account('14705650712', 'zong130720')
        deepseek_pool.add_account('17600700886', 'zong130720')
        deepseek_pool.add_account('19211024947', 'zong130720')
        deepseek_pool.add_account('18602219002', 'zong130720')
        deepseek_pool.add_account('13396414050', 'zhangrui914')
        deepseek_pool.add_account('17602204493', 'zhixia8678')
        deepseek_pool.add_account('13695678303', 'zhixia8678')
        deepseek_pool.add_account('17798045498', 'zhixia8678')

        # 示例4: 添加gemini账号
        print("添加gemini账号...")
        gemini_pool.add_account('m17600700886@163.com', 'zong130720')

        # 示例5: 使用deepseek账号
        print("获取deepseek账号...")
        with deepseek_pool.account(timeout=10) as account:
            if account:
                print(f"获取到deepseek账号: {account['username']}")
                print(f"账号ID: {account['id']}")
                print(f"服务类型: {account['service_type']}")
                print(f"租约到期: {account['lease_expiry']}")

                # 使用账号执行任务...
                time.sleep(2)  # 模拟任务执行
            else:
                print("未获取到deepseek账号")

        # 示例6: 使用gemini账号
        print("获取gemini账号...")
        with gemini_pool.account(timeout=10) as account:
            if account:
                print(f"获取到gemini账号: {account['username']}")
                print(f"账号ID: {account['id']}")
                print(f"服务类型: {account['service_type']}")
                print(f"租约到期: {account['lease_expiry']}")

                # 使用账号执行任务...
                time.sleep(2)  # 模拟任务执行
            else:
                print("未获取到gemini账号")

        # 示例7: 查看所有服务统计
        print("\n所有服务统计:")
        all_services = deepseek_pool.get_all_services()
        for service_type, stats in all_services.items():
            print(f"服务: {service_type}")
            print(f"  总账号数: {stats['total_accounts']}")
            print(f"  可用账号: {stats['available_accounts']}")
            print(f"  本进程锁定: {stats['locked_by_me']}")
            print(f"  总使用次数: {stats['total_uses']}")
            print(f"  平均使用次数: {stats['avg_uses']:.2f}")
            print()

    finally:
        # 关闭连接池
        deepseek_pool.close()
        gemini_pool.close()