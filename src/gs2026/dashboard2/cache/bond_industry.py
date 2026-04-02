"""
债券-行业映射缓存
用于债券上攻排行的行业信息快速查询

设计思路:
- 从 stock_bond_mapping 提取债券→行业关系
- 以债券代码为 key，直接查询行业
- O(1) 时间复杂度，替代原有的 O(n*m) 反查
"""

import json
from typing import Optional, Dict, List
from datetime import datetime

from gs2026.utils import redis_util, log_util
from gs2026.utils.stock_bond_mapping_cache import get_cache as get_stock_bond_cache

logger = log_util.setup_logger(__file__)

# Redis Key 常量
REDIS_KEY_PREFIX = "bond_industry_mapping"
REDIS_KEY_LATEST_DATE = f"{REDIS_KEY_PREFIX}:latest_date"
REDIS_KEY_META = f"{REDIS_KEY_PREFIX}:meta"


class BondIndustryCache:
    """债券行业映射缓存管理器"""
    
    def __init__(self, redis_client=None):
        if redis_client:
            self.redis = redis_client
        else:
            # 确保Redis已初始化
            if redis_util._redis_client is None:
                redis_util.init_redis()
            self.redis = redis_util._redis_client
    
    def _get_mapping_key(self, date: str) -> str:
        """获取指定日期的映射 Key"""
        return f"{REDIS_KEY_PREFIX}:{date}"
    
    def update_cache(self, force: bool = False) -> Dict:
        """
        更新债券行业映射缓存
        从 stock_bond_mapping 提取债券→行业关系
        
        Args:
            force: 是否强制更新（即使已存在）
        
        Returns:
            更新结果信息
        """
        today = datetime.now().strftime('%Y-%m-%d')
        mapping_key = self._get_mapping_key(today)
        
        # 检查是否已存在
        if not force and self.redis.exists(mapping_key):
            meta = self.get_meta() or {}
            count = self.redis.hlen(mapping_key)
            created_at = meta.get('created_at', 'unknown')
            
            if not meta:
                logger.info(f"债券行业缓存存在但无元数据，重新生成: {count} 条")
                # 继续执行更新逻辑
            else:
                logger.info(f"债券行业缓存已存在: {created_at}, 共 {count} 条")
                return {
                    "success": True,
                    "message": f"缓存已存在，共 {count} 条",
                    "date": today,
                    "exists": True,
                    "count": count
                }
        
        try:
            # 从 stock_bond_mapping 获取数据
            logger.info("开始生成债券行业映射...")
            
            stock_bond_cache = get_stock_bond_cache()
            if not stock_bond_cache.ensure_cache():
                return {
                    "success": False,
                    "message": "股票债券映射缓存不可用",
                    "date": today,
                    "count": 0
                }
            
            # 获取全部映射
            all_mappings = stock_bond_cache.get_all_mapping()
            
            if not all_mappings:
                return {
                    "success": False,
                    "message": "股票债券映射数据为空",
                    "date": today,
                    "count": 0
                }
            
            # 提取债券→行业关系
            bond_industry_map = {}
            for stock_code, mapping in all_mappings.items():
                bond_code = mapping.get('bond_code')
                industry_name = mapping.get('industry_name', '-')
                bond_name = mapping.get('bond_name', '')
                
                # 只保存有债券代码的记录
                if bond_code and bond_code.strip():
                    bond_industry_map[bond_code] = {
                        "bond_code": bond_code,
                        "bond_name": bond_name,
                        "industry_name": industry_name if industry_name else '-'
                    }
            
            total_count = len(bond_industry_map)
            logger.info(f"生成债券行业映射: {total_count} 条")
            
            if total_count == 0:
                return {
                    "success": False,
                    "message": "无有效债券映射数据",
                    "date": today,
                    "count": 0
                }
            
            # 使用 Pipeline 批量写入
            pipe = self.redis.pipeline()
            
            for bond_code, data in bond_industry_map.items():
                pipe.hset(mapping_key, bond_code, json.dumps(data, ensure_ascii=False))
            
            # 设置 7 天过期
            pipe.expire(mapping_key, 7 * 24 * 3600)
            
            # 更新最新日期标记
            pipe.set(REDIS_KEY_LATEST_DATE, today)
            
            # 更新元数据
            meta = {
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "total_count": total_count,
                "source": "stock_bond_mapping",
                "version": "1.0"
            }
            pipe.set(REDIS_KEY_META, json.dumps(meta))
            
            # 执行 Pipeline
            pipe.execute()
            
            logger.info(f"债券行业缓存更新成功: {mapping_key}, 共 {total_count} 条")
            
            return {
                "success": True,
                "message": "缓存更新成功",
                "date": today,
                "count": total_count,
                "exists": False
            }
            
        except Exception as e:
            logger.error(f"更新债券行业缓存失败: {e}")
            return {
                "success": False,
                "message": f"更新失败: {str(e)}",
                "date": today,
                "count": 0
            }
    
    def get_industry(self, bond_code: str, date: str = None) -> Optional[str]:
        """
        获取单个债券的行业（O(1)查询）
        
        Args:
            bond_code: 债券代码
            date: 指定日期，默认使用最新日期
        
        Returns:
            行业名称，不存在返回 None
        """
        if date is None:
            date = self.get_latest_date()
        
        if date is None:
            return None
        
        mapping_key = self._get_mapping_key(date)
        data = self.redis.hget(mapping_key, str(bond_code))
        
        if data:
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            mapping = json.loads(data)
            return mapping.get('industry_name', '-')
        return None
    
    def get_industries_batch(self, bond_codes: List[str], date: str = None) -> Dict[str, str]:
        """
        批量获取债券行业（Pipeline优化）
        
        Args:
            bond_codes: 债券代码列表
            date: 指定日期，默认使用最新日期
        
        Returns:
            {bond_code: industry_name} 字典
        """
        if date is None:
            date = self.get_latest_date()
        
        if date is None or not bond_codes:
            return {code: '-' for code in bond_codes}
        
        mapping_key = self._get_mapping_key(date)
        
        # 使用Pipeline批量查询
        pipe = self.redis.pipeline()
        for code in bond_codes:
            pipe.hget(mapping_key, str(code))
        
        results = pipe.execute()
        
        # 构建结果字典
        industry_map = {}
        for code, data in zip(bond_codes, results):
            if data:
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                mapping = json.loads(data)
                industry_map[code] = mapping.get('industry_name', '-')
            else:
                industry_map[code] = '-'
        
        return industry_map
    
    def get_latest_date(self) -> Optional[str]:
        """获取最新映射日期"""
        date = self.redis.get(REDIS_KEY_LATEST_DATE)
        return date.decode('utf-8') if date else None
    
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
        检查缓存是否有效（是否为今天）
        
        Returns:
            True: 缓存有效
            False: 缓存不存在或过期
        """
        latest_date = self.get_latest_date()
        if latest_date is None:
            return False
        
        today = datetime.now().strftime('%Y-%m-%d')
        return latest_date == today
    
    def ensure_cache(self, **kwargs) -> bool:
        """
        确保缓存存在（不存在则自动创建）
        
        Returns:
            True: 缓存可用
            False: 创建失败
        """
        if self.is_cache_valid():
            return True
        
        result = self.update_cache(**kwargs)
        return result["success"]


# 全局缓存实例
cache = None

def get_cache() -> BondIndustryCache:
    """获取全局缓存实例（单例模式）"""
    global cache
    if cache is None:
        cache = BondIndustryCache()
    return cache


def warmup_bond_industry() -> dict:
    """
    预热债券行业缓存（供 CacheManager 调用）
    
    Returns:
        {'success': bool, 'count': int, 'message': str}
    """
    try:
        cache = get_cache()
        if cache is None:
            return {
                'success': False,
                'message': '获取缓存实例失败',
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
        logger.error(f"债券行业缓存预热失败: {e}\n{error_detail}")
        return {
            'success': False,
            'message': f'预热失败: {str(e)}',
            'count': 0
        }


def init_cache():
    """注册到缓存管理器"""
    from .manager import cache_manager, CacheConfig, WarmupMode, CachePriority
    
    cache_manager.register(CacheConfig(
        name="bond_industry",
        warmup_func=warmup_bond_industry,
        mode=WarmupMode.ASYNC,
        priority=CachePriority.NORMAL,
        timeout=60,
        retry=2
    ))
