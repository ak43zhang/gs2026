"""
行业股票计数缓存
从 data_industry_code_component_ths 表统计各行业股票数量

设计思路（参考 stock_bond_mapping_cache.py）:
1. 使用类封装缓存逻辑
2. 支持缓存预热、查询、状态检查
3. 使用 Redis Hash 存储
4. 支持批量查询优化
"""

import json
from typing import Optional, Dict, List
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text

from gs2026.utils import redis_util, log_util, config_util

logger = log_util.setup_logger(__file__)

# Redis Key 常量
REDIS_KEY_INDUSTRY_STOCK_COUNT = "industry_stock_count"
REDIS_KEY_META = "industry_stock_count:meta"


class IndustryStockCache:
    """行业股票计数缓存管理器"""
    
    def __init__(self, redis_client=None):
        if redis_client:
            self.redis = redis_client
        else:
            # 确保Redis已初始化
            if redis_util._redis_client is None:
                try:
                    redis_util.init_redis()
                except Exception as e:
                    logger.error(f"Redis 初始化失败: {e}")
                    raise RuntimeError(f"Redis 初始化失败: {e}")
            
            if redis_util._redis_client is None:
                raise RuntimeError("Redis 客户端未初始化")
            
            self.redis = redis_util._redis_client
    
    def update_cache(self, force: bool = False) -> Dict:
        """
        更新行业股票计数缓存
        
        Args:
            force: 是否强制更新（即使已存在）
        
        Returns:
            更新结果信息
        """
        # 检查是否已存在
        if not force and self.redis.exists(REDIS_KEY_INDUSTRY_STOCK_COUNT):
            meta = self.get_meta() or {}
            created_at = meta.get('created_at', 'unknown')
            logger.info(f"行业股票计数缓存已存在: {created_at}")
            return {
                "success": True,
                "message": "缓存已存在，跳过更新",
                "exists": True,
                "count": meta.get('total_industries', 0)
            }
        
        try:
            # 从数据库统计
            logger.info("开始统计行业股票数量...")
            
            url = config_util.get_config("common.url")
            engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
            
            sql = """
                SELECT 
                    code as industry_code,
                    name as industry_name,
                    COUNT(*) as total_stocks
                FROM data_industry_code_component_ths
                WHERE code IS NOT NULL AND code != ''
                GROUP BY code, name
            """
            
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            
            if df.empty:
                logger.warning("行业成分股统计为空")
                return {
                    "success": False,
                    "message": "行业成分股统计为空",
                    "count": 0
                }
            
            total_count = len(df)
            logger.info(f"统计到 {total_count} 个行业")
            
            # 使用 Pipeline 批量写入
            pipe = self.redis.pipeline()
            
            for _, row in df.iterrows():
                data = {
                    'industry_code': str(row['industry_code']),
                    'industry_name': str(row['industry_name']),
                    'total_stocks': int(row['total_stocks'])
                }
                pipe.hset(
                    REDIS_KEY_INDUSTRY_STOCK_COUNT,
                    str(row['industry_code']),
                    json.dumps(data, ensure_ascii=False)
                )
            
            # 设置 7 天过期
            pipe.expire(REDIS_KEY_INDUSTRY_STOCK_COUNT, 7 * 24 * 3600)
            
            # 更新元数据
            meta = {
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "total_industries": total_count,
                "version": "1.0"
            }
            pipe.set(REDIS_KEY_META, json.dumps(meta))
            
            # 执行 Pipeline
            pipe.execute()
            
            logger.info(f"行业股票计数缓存更新成功: 共 {total_count} 个行业")
            
            return {
                "success": True,
                "message": "缓存更新成功",
                "count": total_count,
                "exists": False
            }
            
        except Exception as e:
            logger.error(f"更新行业股票计数缓存失败: {e}")
            return {
                "success": False,
                "message": f"更新失败: {str(e)}",
                "count": 0
            }
    
    def get_industry_count(self, industry_code: str) -> Optional[Dict]:
        """
        获取单个行业的股票数量
        
        Args:
            industry_code: 行业代码
        
        Returns:
            行业数据字典，不存在返回 None
        """
        data = self.redis.hget(REDIS_KEY_INDUSTRY_STOCK_COUNT, str(industry_code))
        if data:
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            return json.loads(data)
        return None
    
    def get_all_counts(self) -> Dict[str, Dict]:
        """
        获取所有行业的股票数量
        
        Returns:
            {industry_code: industry_data} 字典
        """
        all_data = self.redis.hgetall(REDIS_KEY_INDUSTRY_STOCK_COUNT)
        result = {}
        for code, data in all_data.items():
            if isinstance(code, bytes):
                code = code.decode('utf-8')
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            result[code] = json.loads(data)
        return result
    
    def get_meta(self) -> Optional[Dict]:
        """获取缓存元数据"""
        meta = self.redis.get(REDIS_KEY_META)
        if meta:
            if isinstance(meta, bytes):
                meta = meta.decode('utf-8')
            return json.loads(meta)
        return None
    
    def is_cache_valid(self) -> bool:
        """
        检查缓存是否有效（是否存在且未过期）
        
        Returns:
            True: 缓存有效
            False: 缓存不存在或已过期
        """
        return self.redis.exists(REDIS_KEY_INDUSTRY_STOCK_COUNT) > 0
    
    def ensure_cache(self, force: bool = False) -> bool:
        """
        确保缓存存在（不存在则自动创建）
        
        Args:
            force: 是否强制更新
        
        Returns:
            True: 缓存可用
            False: 创建失败
        """
        if not force and self.is_cache_valid():
            return True
        
        result = self.update_cache(force=force)
        return result["success"]


# 全局缓存实例
cache = None

def get_cache() -> IndustryStockCache:
    """获取全局缓存实例（单例模式）"""
    global cache
    if cache is None:
        cache = IndustryStockCache()
    return cache


def warmup_industry_stock_count() -> dict:
    """
    预热行业股票计数缓存（供 CacheManager 调用）
    
    Returns:
        {'success': bool, 'count': int, 'message': str}
    """
    try:
        cache = get_cache()
        if cache is None:
            return {
                'success': False,
                'message': '获取缓存实例失败: get_cache() 返回 None',
                'count': 0
            }
        
        result = cache.update_cache()
        if result is None:
            return {
                'success': False,
                'message': 'update_cache() 返回 None',
                'count': 0
            }
        
        return {
            'success': result.get('success', False),
            'message': result.get('message', '未知状态'),
            'count': result.get('count', 0),
            'exists': result.get('exists', False)
        }
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"行业股票计数缓存预热失败: {e}\n{error_detail}")
        return {
            'success': False,
            'message': f'预热失败: {str(e)}',
            'count': 0
        }


def init_cache():
    """注册到缓存管理器"""
    from .manager import cache_manager, CacheConfig, WarmupMode, CachePriority
    
    cache_manager.register(CacheConfig(
        name="industry_stock_count",
        warmup_func=warmup_industry_stock_count,
        mode=WarmupMode.ASYNC,
        priority=CachePriority.NORMAL,
        timeout=60,
        retry=2
    ))
