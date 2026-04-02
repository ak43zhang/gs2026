"""
统一缓存管理器
支持缓存注册、预热、状态监控
"""

import threading
import time
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
from enum import Enum


class WarmupMode(Enum):
    """预热模式"""
    SYNC = "sync"      # 同步执行（阻塞）
    ASYNC = "async"    # 异步执行（后台线程）


class CachePriority(Enum):
    """缓存优先级"""
    CRITICAL = 1   # 关键（必须成功）
    HIGH = 2       # 高（建议成功）
    NORMAL = 3     # 正常（可选）


@dataclass
class CacheConfig:
    """缓存配置"""
    name: str                      # 缓存名称
    warmup_func: Callable          # 预热函数
    mode: WarmupMode = WarmupMode.ASYNC
    priority: CachePriority = CachePriority.NORMAL
    timeout: int = 60              # 超时时间（秒）
    retry: int = 1                 # 重试次数


class CacheManager:
    """统一缓存管理器（单例）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._caches: Dict[str, CacheConfig] = {}
        self._results: Dict[str, dict] = {}
        self._initialized = True
    
    def register(self, config: CacheConfig) -> 'CacheManager':
        """
        注册缓存
        
        使用示例:
            cache_manager.register(CacheConfig(
                name="stock_bond_mapping",
                warmup_func=warmup_stock_bond_mapping,
                mode=WarmupMode.ASYNC,
                priority=CachePriority.HIGH
            ))
        """
        self._caches[config.name] = config
        print(f"[CacheManager] 注册缓存: {config.name} ({config.mode.value})")
        return self
    
    def warmup_all(self, sync_names: List[str] = None) -> Dict[str, dict]:
        """
        预热所有缓存
        
        Args:
            sync_names: 强制同步执行的缓存名称列表
            
        Returns:
            各缓存预热结果 {name: result}
        """
        sync_names = sync_names or []
        
        # 按优先级排序
        sorted_caches = sorted(
            self._caches.values(),
            key=lambda c: c.priority.value
        )
        
        # 分离同步和异步
        sync_caches = [c for c in sorted_caches 
                      if c.mode == WarmupMode.SYNC or c.name in sync_names]
        async_caches = [c for c in sorted_caches 
                       if c.mode == WarmupMode.ASYNC and c.name not in sync_names]
        
        results = {}
        
        # 1. 先执行同步缓存（阻塞）
        print(f"\n{'='*50}")
        print(f"[CacheManager] 开始同步预热 ({len(sync_caches)} 个)")
        print(f"{'='*50}")
        for config in sync_caches:
            result = self._warmup_single(config)
            results[config.name] = result
        
        # 2. 再启动异步缓存（后台）
        if async_caches:
            print(f"\n{'='*50}")
            print(f"[CacheManager] 启动异步预热 ({len(async_caches)} 个)")
            print(f"{'='*50}")
            for config in async_caches:
                thread = threading.Thread(
                    target=self._warmup_single,
                    args=(config,),
                    name=f"CacheWarmup-{config.name}",
                    daemon=True
                )
                thread.start()
        
        self._results = results
        return results
    
    def _warmup_single(self, config: CacheConfig) -> dict:
        """执行单个缓存预热"""
        start_time = time.time()
        
        for attempt in range(config.retry):
            try:
                print(f"[CacheWarmup] [{config.name}] 开始预热...")
                result = config.warmup_func()
                
                elapsed = time.time() - start_time
                success = result.get('success', True) if isinstance(result, dict) else True
                
                result_info = {
                    'name': config.name,
                    'success': success,
                    'elapsed': f"{elapsed:.2f}s",
                    'mode': config.mode.value,
                    'attempt': attempt + 1
                }
                
                if isinstance(result, dict):
                    result_info.update(result)
                
                status = "✅ 成功" if success else "❌ 失败"
                print(f"[CacheWarmup] [{config.name}] {status} ({elapsed:.2f}s)")
                
                return result_info
                
            except Exception as e:
                print(f"[CacheWarmup] [{config.name}] 尝试 {attempt+1}/{config.retry} 失败: {e}")
                if attempt == config.retry - 1:
                    elapsed = time.time() - start_time
                    return {
                        'name': config.name,
                        'success': False,
                        'error': str(e),
                        'elapsed': f"{elapsed:.2f}s",
                        'mode': config.mode.value
                    }
                time.sleep(1)  # 重试间隔
    
    def get_status(self) -> Dict[str, dict]:
        """获取所有缓存状态"""
        return self._results.copy()
    
    def is_ready(self, name: str) -> bool:
        """检查指定缓存是否就绪"""
        return self._results.get(name, {}).get('success', False)


# 全局单例
cache_manager = CacheManager()
