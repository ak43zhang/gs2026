"""
股票-债券-行业映射缓存
"""


def warmup_stock_bond_mapping() -> dict:
    """
    预热股票-债券-行业映射缓存
    
    Returns:
        {'success': bool, 'total_count': int, 'message': str}
    """
    try:
        from gs2026.utils.stock_bond_mapping_cache import get_cache
        
        cache = get_cache()
        
        if cache.is_cache_valid():
            meta = cache.get_meta()
            return {
                'success': True,
                'message': '缓存已存在且有效',
                'total_count': meta.get('total_count', 0),
                'date': cache.get_latest_date()
            }
        
        # 需要更新
        result = cache.update_mapping()
        return result
        
    except Exception as e:
        return {
            'success': False,
            'message': f'股票债券映射缓存预热失败: {str(e)}',
            'total_count': 0
        }


def init_cache():
    """注册到缓存管理器"""
    from .manager import cache_manager, CacheConfig, WarmupMode, CachePriority
    
    cache_manager.register(CacheConfig(
        name="stock_bond_mapping",
        warmup_func=warmup_stock_bond_mapping,
        mode=WarmupMode.ASYNC,      # 异步执行
        priority=CachePriority.HIGH,  # 高优先级
        timeout=120,
        retry=2
    ))
