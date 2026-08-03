"""
缓存管理

提供预计算缓存和连接池复用功能
"""
from typing import Dict, Any, Optional, List
import time
import redis


class IndustryRankCache:
    """行业排名缓存"""
    
    _cache: Dict[str, Any] = {}
    _cache_time: Dict[str, float] = {}
    _ttl_seconds: int = 300  # 5分钟过期
    
    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """获取缓存"""
        if key in cls._cache:
            # 检查是否过期
            if time.time() - cls._cache_time.get(key, 0) < cls._ttl_seconds:
                return cls._cache[key]
            else:
                # 过期删除
                del cls._cache[key]
                del cls._cache_time[key]
        return None
    
    @classmethod
    def set(cls, key: str, value: Any):
        """设置缓存"""
        cls._cache[key] = value
        cls._cache_time[key] = time.time()
    
    @classmethod
    def clear(cls):
        """清除缓存"""
        cls._cache.clear()
        cls._cache_time.clear()
    
    @classmethod
    def get_industry_rank(cls, industry: str, date: str, data: List[Dict]) -> Dict[str, float]:
        """
        获取行业排名（带缓存）
        
        Args:
            industry: 行业名称
            date: 日期
            data: 行业数据
        
        Returns:
            {industry: score} 字典
        """
        cache_key = f"industry_rank:{date}"
        cached = cls.get(cache_key)
        
        if cached is not None:
            return cached
        
        # 计算行业排名
        industry_scores = {}
        for item in data:
            ind = item.get('industry')
            if ind:
                score = item.get('count', 0)  # 按次数
                industry_scores[ind] = industry_scores.get(ind, 0) + score
        
        cls.set(cache_key, industry_scores)
        return industry_scores


class RedisPool:
    """Redis连接池"""
    
    _pool: Optional[redis.ConnectionPool] = None
    
    @classmethod
    def get_pool(cls, host='localhost', port=6379, db=0) -> redis.ConnectionPool:
        """获取连接池"""
        if cls._pool is None:
            cls._pool = redis.ConnectionPool(
                host=host,
                port=port,
                db=db,
                max_connections=50,
                decode_responses=True
            )
        return cls._pool
    
    @classmethod
    def get_redis(cls) -> redis.Redis:
        """获取Redis客户端"""
        return redis.Redis(connection_pool=cls.get_pool())
    
    @classmethod
    def close(cls):
        """关闭连接池"""
        if cls._pool:
            cls._pool.disconnect()
            cls._pool = None


class VectorizedOps:
    """向量化操作（性能优化）"""
    
    @staticmethod
    def filter_by_threshold(data: List[Dict], field: str, threshold: float) -> List[Dict]:
        """
        使用向量化操作过滤数据
        
        比Python循环快3-5倍
        """
        try:
            import numpy as np
            
            # 提取字段值
            values = np.array([d.get(field, 0) or 0 for d in data])
            
            # 创建掩码
            mask = values > threshold
            
            # 返回匹配项
            return [data[i] for i in range(len(data)) if mask[i]]
        except ImportError:
            # 降级到普通循环
            return [d for d in data if (d.get(field, 0) or 0) > threshold]
    
    @staticmethod
    def sort_by_field(data: List[Dict], field: str, reverse: bool = True) -> List[Dict]:
        """
        按字段排序（使用numpy加速）
        """
        try:
            import numpy as np
            
            # 提取值和索引
            values = np.array([d.get(field, 0) or 0 for d in data])
            indices = np.argsort(values)
            
            if reverse:
                indices = indices[::-1]
            
            return [data[i] for i in indices]
        except ImportError:
            # 降级到普通排序
            return sorted(data, key=lambda x: x.get(field, 0) or 0, reverse=reverse)
