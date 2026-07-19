"""
可转债分时图Redis缓存 - 可插拔核心模块

设计原则:
1. 可插拔: 通过开关控制，随时启用/禁用
2. 零侵入: 装饰器模式，不修改原有逻辑
3. 渐进式: 分层架构，预留扩展接口
4. 高可用: 自动降级，故障自愈

版本: v1.0 (核心功能)
扩展: 预留Layer 2服务层接口
"""

import json
import logging
import threading
import time
from typing import Optional, Dict, List, Callable, Any
from datetime import datetime, timedelta
from functools import wraps

logger = logging.getLogger(__name__)


# ==================== 配置层 ====================

class CacheConfig:
    """缓存配置 - 集中管理所有配置项"""
    
    # 主开关
    ENABLED = True
    
    # 写入模式
    ASYNC_WRITE = True       # True=异步, False=同步
    BATCH_WRITE = False      # True=批量缓冲, False=单条 (未来扩展)
    
    # 性能参数
    PIPELINE_SIZE = 100      # pipeline批量大小 (未来扩展)
    BUFFER_FLUSH_SEC = 3     # 缓冲刷新间隔 (未来扩展)
    
    # 过期策略
    EXPIRE_HOURS = 16        # 16小时 = 当日有效到次日开盘前
    
    # 容错参数
    MAX_FAIL_COUNT = 3       # 最大容忍失败次数
    RECOVERY_CHECK_SEC = 60  # 恢复检测间隔
    
    # 扩展预留: 恢复服务配置
    RECOVERY_ENABLED = False      # 当前禁用，未来启用
    RECOVERY_ONLY_OFFHOURS = True  # 仅非交易时间恢复
    
    # 扩展预留: 监控配置
    METRICS_ENABLED = False   # 当前禁用，未来启用


# ==================== 核心层 (Layer 1) ====================

class BondTickCache:
    """
    可转债分时图Redis缓存 - 核心类
    
    职责:
    - 单条/批量数据读写
    - 连接管理与健康检查
    - 自动故障降级
    
    扩展点:
    - 通过CacheConfig配置行为
    - 通过回调函数扩展功能
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # 状态
    _enabled = True
    _fail_count = 0
    _redis = None
    _initialized = False
    
    # 扩展预留: 回调钩子
    _on_write_success: Optional[Callable] = None
    _on_write_fail: Optional[Callable] = None
    _on_recovery: Optional[Callable] = None
    
    @classmethod
    def get_instance(cls) -> 'BondTickCache':
        """线程安全的单例获取"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def is_enabled(cls) -> bool:
        """检查是否启用"""
        return cls._enabled and cls._initialized
    
    @classmethod
    def set_enabled(cls, enabled: bool):
        """动态开关"""
        cls._enabled = enabled
        logger.info(f"[BondTickCache] {'启用' if enabled else '禁用'}")
    
    @classmethod
    def register_callback(cls, event: str, callback: Callable):
        """
        注册扩展回调
        
        事件类型:
        - 'write_success': 写入成功
        - 'write_fail': 写入失败
        - 'recovery': 恢复完成
        """
        if event == 'write_success':
            cls._on_write_success = callback
        elif event == 'write_fail':
            cls._on_write_fail = callback
        elif event == 'recovery':
            cls._on_recovery = callback
    
    def __init__(self):
        """初始化Redis连接"""
        if self._initialized:
            return
        
        try:
            from gs2026.utils.redis_util import get_redis_client
            self._redis = get_redis_client()
            self._redis.ping()
            self._initialized = True
            logger.info("[BondTickCache] Redis连接成功")
            
            # 启动健康检查线程
            self._start_health_check()
            
        except Exception as e:
            logger.warning(f"[BondTickCache] Redis连接失败: {e}")
            self._enabled = False
            self._initialized = False
    
    def _start_health_check(self):
        """启动后台健康检查"""
        def check_loop():
            while True:
                time.sleep(CacheConfig.RECOVERY_CHECK_SEC)
                if not self._enabled:
                    self._try_recovery()
        
        thread = threading.Thread(target=check_loop, daemon=True, name="CacheHealthCheck")
        thread.start()
    
    def _try_recovery(self):
        """尝试恢复连接"""
        try:
            if self._redis:
                self._redis.ping()
                self._enabled = True
                self._fail_count = 0
                logger.info("[BondTickCache] Redis已恢复")
                
                # 触发恢复回调
                if self._on_recovery:
                    self._on_recovery()
        except Exception:
            pass
    
    def _handle_error(self, e: Exception):
        """错误处理与降级"""
        self._fail_count += 1
        logger.warning(f"[BondTickCache] 错误({self._fail_count}/{CacheConfig.MAX_FAIL_COUNT}): {e}")
        
        if self._fail_count >= CacheConfig.MAX_FAIL_COUNT:
            self._enabled = False
            logger.error("[BondTickCache] 连续失败，自动降级到MySQL")
            
            if self._on_write_fail:
                self._on_write_fail(self._fail_count)
    
    def _get_key(self, bond_code: str, date: Optional[str] = None) -> str:
        """生成数据Key"""
        date = date or datetime.now().strftime('%Y%m%d')
        return f"bond:tick:{bond_code}:{date}"
    
    def _get_index_key(self, date: Optional[str] = None) -> str:
        """生成索引Key"""
        date = date or datetime.now().strftime('%Y%m%d')
        return f"bond:tick:index:{date}"
    
    # ==================== 写入接口 ====================
    
    def write(self, bond_code: str, time_str: str, data: Dict) -> bool:
        """
        同步写入
        
        性能: ~2-5ms (pipeline优化)
        """
        if not self._enabled or not self._redis:
            return False
        
        try:
            key = self._get_key(bond_code)
            index_key = self._get_index_key()
            json_data = json.dumps(data, ensure_ascii=False, default=str)
            
            # Pipeline批量操作
            pipe = self._redis.pipeline()
            pipe.hset(key, time_str, json_data)
            pipe.sadd(index_key, bond_code)
            pipe.expire(key, CacheConfig.EXPIRE_HOURS * 3600)
            pipe.expire(index_key, CacheConfig.EXPIRE_HOURS * 3600)
            pipe.execute()
            
            self._fail_count = 0  # 重置失败计数
            
            # 触发成功回调
            if self._on_write_success:
                self._on_write_success(bond_code, time_str)
            
            return True
            
        except Exception as e:
            self._handle_error(e)
            return False
    
    def write_async(self, bond_code: str, time_str: str, data: Dict):
        """
        异步写入 - 主流程调用
        
        特点:
        - 零阻塞，立即返回
        - 后台线程执行
        - 失败不影响主流程
        """
        if not self._enabled:
            return
        
        if CacheConfig.ASYNC_WRITE:
            threading.Thread(
                target=self.write,
                args=(bond_code, time_str, data),
                daemon=True,
                name=f"RedisWrite-{bond_code}"
            ).start()
        else:
            # 同步模式（调试用）
            self.write(bond_code, time_str, data)
    
    def write_batch(self, bond_code: str, ticks: List[Dict]) -> bool:
        """
        批量写入 - 预留接口
        
        用于:
        - 初始化加载
        - 从MySQL恢复
        - 历史数据回填
        """
        if not self._enabled or not self._redis:
            return False
        
        try:
            key = self._get_key(bond_code)
            index_key = self._get_index_key()
            
            # 构造批量数据
            mapping = {}
            for tick in ticks:
                time_str = tick.get('time', '')
                if time_str:
                    mapping[time_str] = json.dumps(tick, ensure_ascii=False, default=str)
            
            if not mapping:
                return False
            
            # Pipeline执行
            pipe = self._redis.pipeline()
            pipe.hset(key, mapping=mapping)
            pipe.sadd(index_key, bond_code)
            pipe.expire(key, CacheConfig.EXPIRE_HOURS * 3600)
            pipe.expire(index_key, CacheConfig.EXPIRE_HOURS * 3600)
            pipe.execute()
            
            logger.info(f"[BondTickCache] 批量写入 {bond_code}: {len(ticks)}条")
            return True
            
        except Exception as e:
            self._handle_error(e)
            return False
    
    # ==================== 查询接口 ====================
    
    def get_all(self, bond_code: str, date: Optional[str] = None) -> List[Dict]:
        """
        获取单债券全天数据
        
        Returns:
            按time排序的tick列表
        """
        if not self._enabled or not self._redis:
            return []
        
        try:
            key = self._get_key(bond_code, date)
            data = self._redis.hgetall(key)
            
            if not data:
                return []
            
            ticks = []
            for time_str, json_data in data.items():
                tick = json.loads(json_data)
                tick['time'] = time_str.decode() if isinstance(time_str, bytes) else time_str
                ticks.append(tick)
            
            ticks.sort(key=lambda x: x['time'])
            return ticks
            
        except Exception as e:
            logger.warning(f"[BondTickCache] 读取失败: {e}")
            return []
    
    def get_time_range(self, bond_code: str, start_time: str, end_time: str, 
                       date: Optional[str] = None) -> List[Dict]:
        """
        获取时间范围数据 - 预留接口
        """
        all_ticks = self.get_all(bond_code, date)
        return [t for t in all_ticks if start_time <= t['time'] <= end_time]
    
    def exists(self, bond_code: str, date: Optional[str] = None) -> bool:
        """检查债券数据是否存在"""
        if not self._enabled or not self._redis:
            return False
        
        try:
            key = self._get_key(bond_code, date)
            return self._redis.exists(key) > 0
        except Exception:
            return False
    
    # ==================== 管理接口 ====================
    
    def clear(self, date: Optional[str] = None) -> int:
        """
        清理数据 - 预留接口
        
        用于:
        - 定时任务清理过期数据
        - 手动重置缓存
        """
        if not self._redis:
            return 0
        
        date = date or datetime.now().strftime('%Y%m%d')
        
        try:
            index_key = self._get_index_key(date)
            bond_codes = self._redis.smembers(index_key)
            
            pipe = self._redis.pipeline()
            count = 0
            
            for code in bond_codes:
                code = code.decode() if isinstance(code, bytes) else code
                key = self._get_key(code, date)
                pipe.delete(key)
                count += 1
            
            pipe.delete(index_key)
            pipe.execute()
            
            logger.info(f"[BondTickCache] 清理 {date}: {count}个债券")
            return count
            
        except Exception as e:
            logger.error(f"[BondTickCache] 清理失败: {e}")
            return 0
    
    def get_stats(self) -> Dict:
        """
        获取统计信息 - 预留接口
        
        用于监控:
        - 缓存命中率
        - 内存使用量
        - 连接状态
        """
        if not self._redis:
            return {'status': 'down'}
        
        try:
            date = datetime.now().strftime('%Y%m%d')
            index_key = self._get_index_key(date)
            total_bonds = self._redis.scard(index_key)
            
            return {
                'status': 'up' if self._enabled else 'degraded',
                'enabled': self._enabled,
                'initialized': self._initialized,
                'total_bonds_cached': total_bonds,
                'fail_count': self._fail_count,
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


# ==================== 快捷函数 ====================

def write_tick_async(bond_code: str, time_str: str, data: Dict):
    """异步写入快捷函数"""
    cache = BondTickCache.get_instance()
    cache.write_async(bond_code, time_str, data)

def get_bond_ticks(bond_code: str, date: Optional[str] = None) -> List[Dict]:
    """查询快捷函数"""
    cache = BondTickCache.get_instance()
    return cache.get_all(bond_code, date)

def is_cache_enabled() -> bool:
    """检查缓存是否启用"""
    return BondTickCache.is_enabled()


# ==================== 装饰器 ====================

def redis_cache_enabled(func):
    """
    可插拔装饰器
    
    用法:
        @redis_cache_enabled
        def my_function():
            pass
    
    特性:
    - 自动检查缓存状态
    - 禁用时不执行被装饰函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not BondTickCache.is_enabled():
            return None
        return func(*args, **kwargs)
    return wrapper
