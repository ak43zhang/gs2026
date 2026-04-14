"""
缓存管理统一入口

使用示例:
    from gs2026.dashboard2.cache import cache_manager, init_all_caches
    
    # 注册所有缓存
    init_all_caches()
    
    # 预热所有缓存
    cache_manager.warmup_all(sync_names=['red_list'])
"""

from .manager import cache_manager, CacheManager, WarmupMode, CachePriority


def init_all_caches():
    """初始化并注册所有缓存"""
    # 按依赖顺序注册
    
    # 1. 红名单缓存（关键，同步）
    from . import red_list
    red_list.init_cache()
    
    # 2. 债券绿名单缓存（关键，同步）
    from . import green_bond_list
    green_bond_list.init_cache()
    
    # 3. 股票债券映射（高优先级，异步）
    from . import stock_bond_mapping
    stock_bond_mapping.init_cache()
    
    # 4. 行业股票计数（普通，异步）
    from . import industry_stock
    industry_stock.init_cache()
    
    # 5. 债券行业映射（普通，异步，依赖 stock_bond_mapping）
    from . import bond_industry
    bond_industry.init_cache()
    
    print(f"\n[CacheManager] 共注册 {len(cache_manager._caches)} 个缓存")


__all__ = [
    'cache_manager',
    'init_all_caches',
    'CacheManager',
    'WarmupMode',
    'CachePriority'
]
