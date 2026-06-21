"""通用分布式锁管理器

支持多进程任务调度，提供锁的获取、释放、批量操作等功能。
"""
from typing import Callable, List, Any, Optional
import redis


class DistributedLockManager:
    """通用分布式锁管理器，支持多进程任务调度
    
    Typical usage::
    
        from gs2026.utils.distributed_lock import DistributedLockManager
        
        lock_mgr = DistributedLockManager(redis_client, lock_timeout=900)
        
        # 过滤已锁定
        available = lock_mgr.filter_locked(items, key_func=lambda x: f"lock:{x[0]}")
        
        # 批量加锁
        locked = lock_mgr.batch_try_lock(available, key_func=lambda x: f"lock:{x[0]}")
        
        try:
            # 处理加锁成功的记录
            for item, lock in locked:
                process(item)
        finally:
            lock_mgr.release_all()
    """
    
    def __init__(self, redis_client: redis.Redis, lock_timeout: int = 900):
        """
        Args:
            redis_client: Redis客户端实例
            lock_timeout: 锁超时时间（秒），默认15分钟
        """
        self.redis = redis_client
        self.lock_timeout = lock_timeout
        self._locks: List[redis.lock.Lock] = []
    
    def is_locked(self, lock_key: str) -> bool:
        """检查是否已被锁定"""
        return self.redis.exists(lock_key)
    
    def try_lock(self, lock_key: str) -> Optional[redis.lock.Lock]:
        """
        尝试获取锁，非阻塞
        
        Args:
            lock_key: 锁键名
            
        Returns:
            成功返回Lock对象，失败返回None
        """
        lock = self.redis.lock(lock_key, timeout=self.lock_timeout, blocking_timeout=0)
        if lock.acquire(blocking=False):
            self._locks.append(lock)
            return lock
        return None
    
    def batch_try_lock(self, items: List[Any], key_func: Callable[[Any], str]) -> List[tuple]:
        """
        批量尝试获取锁
        
        Args:
            items: 待加锁的数据项列表
            key_func: 从数据项生成锁键的函数
            
        Returns:
            成功加锁的 (item, lock) 元组列表
        """
        locked_items = []
        for item in items:
            lock_key = key_func(item)
            lock = self.try_lock(lock_key)
            if lock:
                locked_items.append((item, lock))
        return locked_items
    
    def filter_locked(self, items: List[Any], key_func: Callable[[Any], str]) -> List[Any]:
        """
        过滤掉已被锁定的项
        
        Args:
            items: 数据项列表
            key_func: 从数据项生成锁键的函数
            
        Returns:
            未被锁定的数据项列表
        """
        return [item for item in items if not self.is_locked(key_func(item))]
    
    def release_lock(self, lock) -> None:
        """释放单个锁"""
        try:
            lock.release()
            if lock in self._locks:
                self._locks.remove(lock)
        except redis.exceptions.LockNotOwnedError:
            pass
        except Exception:
            pass
    
    def release_all(self) -> None:
        """释放所有已获取的锁"""
        for lock in self._locks[:]:
            self.release_lock(lock)
        self._locks.clear()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，确保锁释放"""
        self.release_all()
        return False


class LockContext:
    """锁上下文管理器，用于单个锁的便捷管理
    
    Typical usage::
    
        from gs2026.utils.distributed_lock import LockContext
        
        with LockContext(redis_client, "my_lock", lock_timeout=900) as ctx:
            if ctx.acquired:
                # 执行受保护的操作
                process()
            else:
                # 获取锁失败
                pass
    """
    
    def __init__(self, redis_client: redis.Redis, lock_key: str, lock_timeout: int = 900):
        """
        Args:
            redis_client: Redis客户端实例
            lock_key: 锁键名
            lock_timeout: 锁超时时间（秒）
        """
        self.redis = redis_client
        self.lock_key = lock_key
        self.lock_timeout = lock_timeout
        self.lock = None
        self.acquired = False
    
    def __enter__(self):
        """进入上下文，尝试获取锁"""
        self.lock = self.redis.lock(self.lock_key, timeout=self.lock_timeout, blocking_timeout=0)
        self.acquired = self.lock.acquire(blocking=False)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，释放锁"""
        if self.lock and self.acquired:
            try:
                self.lock.release()
            except redis.exceptions.LockNotOwnedError:
                pass
        return False


def with_distributed_lock(redis_client: redis.Redis, lock_key: str, lock_timeout: int = 900):
    """
    创建锁上下文管理器的便捷函数
    
    Args:
        redis_client: Redis客户端实例
        lock_key: 锁键名
        lock_timeout: 锁超时时间（秒）
        
    Returns:
        LockContext上下文管理器
        
    Example::
    
        from gs2026.utils.distributed_lock import with_distributed_lock
        
        with with_distributed_lock(redis_client, "my_lock") as ctx:
            if ctx.acquired:
                process()
    """
    return LockContext(redis_client, lock_key, lock_timeout)
