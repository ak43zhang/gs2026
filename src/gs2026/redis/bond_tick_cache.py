"""
可转债分时图Redis缓存 - 纯消费者模式

设计原则:
1. 零连接：复用Dashboard2全局Redis连接池，不创建新连接
2. 零配置：无需额外初始化，即插即用
3. 天然降级：每次操作获取客户端，不可用时自动跳过
4. 可插拔：通过CacheConfig.ENABLED开关控制
"""

import json
import time
import logging
import threading
from typing import Optional, Dict, List
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)


# ==================== 配置 ====================

class CacheConfig:
    """缓存配置"""
    ENABLED = True           # 主开关
    ASYNC_WRITE = True       # 异步写入
    EXPIRE_HOURS = 16        # 16小时过期
    MAX_FAIL_COUNT = 3       # 连续失败N次后降级
    DEGRADE_SECONDS = 60     # 降级持续秒数


# ==================== 核心类 ====================

class BondTickCache:
    """
    可转债分时图Redis缓存 - 纯消费者模式
    
    不创建Redis连接，复用Dashboard2全局连接池。
    每次操作时获取客户端，天然支持故障降级。
    """
    
    _instance = None
    _fail_count = 0
    _disabled_until = 0  # 降级恢复时间戳
    
    @classmethod
    def get_instance(cls) -> 'BondTickCache':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def _redis(cls):
        """
        复用全局Redis连接池（零额外连接）
        
        降级逻辑：连续失败3次 → 停用60秒 → 自动恢复
        """
        # 降级中：检查是否到了恢复时间
        if cls._disabled_until > 0:
            if time.time() < cls._disabled_until:
                return None
            # 恢复
            cls._disabled_until = 0
            cls._fail_count = 0
            logger.info("[BondTickCache] 降级恢复，重新启用")
        
        from gs2026.utils.redis_util import _get_redis_client
        return _get_redis_client()
    
    @classmethod
    def is_enabled(cls) -> bool:
        """是否可用（配置开关 + Redis就绪）"""
        if not CacheConfig.ENABLED:
            return False
        return cls._redis() is not None
    
    @classmethod
    def set_enabled(cls, enabled: bool):
        """动态开关"""
        CacheConfig.ENABLED = enabled
    
    @classmethod
    def _on_fail(cls, e=None):
        """失败计数，连续N次后降级"""
        cls._fail_count += 1
        if e:
            logger.debug(f"[BondTickCache] 操作失败({cls._fail_count}): {e}")
        if cls._fail_count >= CacheConfig.MAX_FAIL_COUNT:
            cls._disabled_until = time.time() + CacheConfig.DEGRADE_SECONDS
            logger.warning(f"[BondTickCache] 连续{cls._fail_count}次失败，降级{CacheConfig.DEGRADE_SECONDS}秒")
    
    @classmethod
    def _on_success(cls):
        """成功时重置计数"""
        if cls._fail_count > 0:
            cls._fail_count = 0
    
    @staticmethod
    def _today():
        return datetime.now().strftime('%Y%m%d')
    
    # ==================== 写入 ====================
    
    def write(self, bond_code: str, time_str: str, data: Dict) -> bool:
        """同步写入单条"""
        r = self._redis()
        if not r:
            return False
        try:
            date = data.get('_date') or self._today()
            key = f"bond:tick:{bond_code}:{date}"
            index_key = f"bond:tick:index:{date}"
            json_data = json.dumps(data, ensure_ascii=False, default=str)
            
            pipe = r.pipeline()
            pipe.hset(key, time_str, json_data)
            pipe.sadd(index_key, bond_code)
            pipe.expire(key, CacheConfig.EXPIRE_HOURS * 3600)
            pipe.expire(index_key, CacheConfig.EXPIRE_HOURS * 3600)
            pipe.execute()
            
            self._on_success()
            return True
        except Exception as e:
            self._on_fail(e)
            return False
    
    def write_async(self, bond_code: str, time_str: str, data: Dict):
        """异步写入（零阻塞）"""
        if not CacheConfig.ENABLED:
            return
        if CacheConfig.ASYNC_WRITE:
            threading.Thread(
                target=self.write,
                args=(bond_code, time_str, data),
                daemon=True
            ).start()
        else:
            self.write(bond_code, time_str, data)
    
    def write_batch(self, bond_code: str, ticks: List[Dict], date: str = None) -> bool:
        """批量写入"""
        r = self._redis()
        if not r:
            return False
        try:
            date = date or self._today()
            key = f"bond:tick:{bond_code}:{date}"
            index_key = f"bond:tick:index:{date}"
            
            mapping = {}
            for tick in ticks:
                t = tick.get('time', '')
                if t:
                    mapping[t] = json.dumps(tick, ensure_ascii=False, default=str)
            
            if not mapping:
                return False
            
            pipe = r.pipeline()
            pipe.hset(key, mapping=mapping)
            pipe.sadd(index_key, bond_code)
            pipe.expire(key, CacheConfig.EXPIRE_HOURS * 3600)
            pipe.expire(index_key, CacheConfig.EXPIRE_HOURS * 3600)
            pipe.execute()
            
            self._on_success()
            logger.info(f"[BondTickCache] 批量写入 {bond_code}: {len(mapping)}条")
            return True
        except Exception as e:
            self._on_fail(e)
            return False
    
    # ==================== 查询 ====================
    
    def get_all(self, bond_code: str, date: str = None) -> List[Dict]:
        """获取单债券全天数据"""
        r = self._redis()
        if not r:
            return []
        try:
            date = date or self._today()
            key = f"bond:tick:{bond_code}:{date}"
            data = r.hgetall(key)
            
            if not data:
                return []
            
            ticks = []
            for t, v in data.items():
                tick = json.loads(v)
                tick['time'] = t.decode() if isinstance(t, bytes) else t
                ticks.append(tick)
            
            ticks.sort(key=lambda x: x['time'])
            self._on_success()
            return ticks
        except Exception as e:
            self._on_fail(e)
            return []
    
    def exists(self, bond_code: str, date: str = None) -> bool:
        """检查是否存在"""
        r = self._redis()
        if not r:
            return False
        try:
            date = date or self._today()
            return r.exists(f"bond:tick:{bond_code}:{date}") > 0
        except Exception:
            return False
    
    # ==================== 管理 ====================
    
    def clear(self, date: str = None) -> int:
        """清理指定日期数据"""
        r = self._redis()
        if not r:
            return 0
        try:
            date = date or self._today()
            index_key = f"bond:tick:index:{date}"
            codes = r.smembers(index_key)
            
            pipe = r.pipeline()
            for code in codes:
                code = code.decode() if isinstance(code, bytes) else code
                pipe.delete(f"bond:tick:{code}:{date}")
            pipe.delete(index_key)
            pipe.execute()
            
            return len(codes)
        except Exception:
            return 0
    
    def get_stats(self) -> Dict:
        """获取统计"""
        r = self._redis()
        if not r:
            return {'status': 'unavailable'}
        try:
            date = self._today()
            index_key = f"bond:tick:index:{date}"
            total = r.scard(index_key)
            return {
                'status': 'up' if self._disabled_until == 0 else 'degraded',
                'total_bonds_cached': total,
                'fail_count': self._fail_count,
            }
        except Exception:
            return {'status': 'error'}


# ==================== 快捷函数 ====================

def write_tick_async(bond_code: str, time_str: str, data: Dict):
    """异步写入"""
    BondTickCache.get_instance().write_async(bond_code, time_str, data)

def get_bond_ticks(bond_code: str, date: str = None) -> List[Dict]:
    """查询"""
    return BondTickCache.get_instance().get_all(bond_code, date)

def is_cache_enabled() -> bool:
    """检查是否启用"""
    return BondTickCache.is_enabled()


# ==================== 装饰器 ====================

def redis_cache_enabled(func):
    """可插拔装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not BondTickCache.is_enabled():
            return None
        return func(*args, **kwargs)
    return wrapper
