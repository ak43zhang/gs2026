"""
Redis缓存模块 - 可插拔式可转债分时图缓存（纯消费者模式）

复用Dashboard2全局Redis连接池，零额外连接。

使用方式:
    from gs2026.redis import write_tick_async, get_bond_ticks
    
    # 写入
    write_tick_async('110072', '09:30:03', {...})
    
    # 查询
    ticks = get_bond_ticks('110072', '20260717')
"""

from .bond_tick_cache import (
    BondTickCache,
    CacheConfig,
    write_tick_async,
    get_bond_ticks,
    is_cache_enabled,
    redis_cache_enabled,
)

from .bond_tick_api import (
    bp as bond_tick_blueprint,
    init_app,
)

__all__ = [
    'BondTickCache',
    'CacheConfig',
    'write_tick_async',
    'get_bond_ticks',
    'is_cache_enabled',
    'redis_cache_enabled',
    'bond_tick_blueprint',
    'init_app',
]

__version__ = '1.1.0'
