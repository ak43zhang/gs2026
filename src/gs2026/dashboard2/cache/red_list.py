"""
红名单缓存
"""


def warmup_red_list() -> dict:
    """
    预热红名单缓存
    
    Returns:
        {'success': bool, 'count': int, 'message': str}
    """
    try:
        from gs2026.dashboard2.routes.red_list_cache import init_red_list_on_startup
        result = init_red_list_on_startup()
        return {
            'success': True,
            'message': result.get('message', '红名单缓存初始化完成'),
            'count': result.get('count', 0)
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'红名单缓存预热失败: {str(e)}',
            'count': 0
        }


def init_cache():
    """注册到缓存管理器"""
    from .manager import cache_manager, CacheConfig, WarmupMode, CachePriority
    
    cache_manager.register(CacheConfig(
        name="red_list",
        warmup_func=warmup_red_list,
        mode=WarmupMode.SYNC,        # 同步执行（关键）
        priority=CachePriority.CRITICAL,
        timeout=30,
        retry=1
    ))
