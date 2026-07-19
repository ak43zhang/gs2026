"""
Redis缓存模块 - 可插拔式可转债分时图缓存

模块结构:
- bond_tick_cache.py: 核心缓存类
- bond_tick_api.py: Flask API路由
- recovery.py: 恢复服务（未来扩展）
- cleanup.py: 清理服务（未来扩展）

使用方式:
    from gs2026.redis import write_tick_async, get_bond_ticks
    
    # 写入（monitor_bond.py中调用）
    write_tick_async('110072', '09:30:03', {...})
    
    # 查询
    ticks = get_bond_ticks('110072')

配置:
    环境变量:
    - BOND_TICK_CACHE_ENABLED=true/false  # 总开关
    
    代码配置:
    from gs2026.redis.bond_tick_cache import CacheConfig
    CacheConfig.ENABLED = True
"""

# 导出核心接口
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
    # 核心类
    'BondTickCache',
    'CacheConfig',
    
    # 快捷函数
    'write_tick_async',
    'get_bond_ticks',
    'is_cache_enabled',
    
    # 装饰器
    'redis_cache_enabled',
    
    # API
    'bond_tick_blueprint',
    'init_app',
]

# 版本信息
__version__ = '1.0.0'
