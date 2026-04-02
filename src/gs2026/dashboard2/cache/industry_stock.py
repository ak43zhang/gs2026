"""
行业股票计数缓存
用于行业排行计算
"""


def warmup_industry_stock_count() -> dict:
    """
    预热行业股票计数缓存
    从 Redis data_industry_code_ths 初始化行业股票数量
    
    Returns:
        {'success': bool, 'count': int, 'message': str}
    """
    try:
        from gs2026.utils import redis_util
        import json
        
        # 确保 Redis 已初始化
        if redis_util._redis_client is None:
            redis_util.init_redis()
        
        redis_client = redis_util._get_redis_client()
        
        # 检查是否已存在
        existing = redis_client.get('data_industry_stock_count')
        if existing:
            count_data = json.loads(existing)
            return {
                'success': True,
                'message': '行业股票计数缓存已存在',
                'count': len(count_data),
                'source': 'redis'
            }
        
        # 从行业成分股数据计算
        industry_data = redis_client.get('data_industry_code_ths')
        if not industry_data:
            return {
                'success': False,
                'message': '行业成分股数据不存在，跳过预热',
                'count': 0
            }
        
        data = json.loads(industry_data)
        
        # 统计每个行业的股票数量
        industry_counts = {}
        for item in data:
            industry_code = item.get('code')
            if industry_code:
                industry_counts[industry_code] = industry_counts.get(industry_code, 0) + 1
        
        # 保存到 Redis
        redis_client.set('data_industry_stock_count', json.dumps(industry_counts))
        
        return {
            'success': True,
            'message': '行业股票计数缓存初始化完成',
            'count': len(industry_counts),
            'source': 'calculated'
        }
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[CacheWarmup] [industry_stock_count] 错误详情:\n{error_detail}")
        return {
            'success': False,
            'message': f'行业股票计数缓存预热失败: {str(e)}',
            'count': 0,
            'error_detail': str(e)
        }


def init_cache():
    """注册到缓存管理器"""
    from .manager import cache_manager, CacheConfig, WarmupMode, CachePriority
    
    cache_manager.register(CacheConfig(
        name="industry_stock_count",
        warmup_func=warmup_industry_stock_count,
        mode=WarmupMode.ASYNC,      # 异步执行
        priority=CachePriority.NORMAL,
        timeout=30,
        retry=1
    ))
