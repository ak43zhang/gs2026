"""
债券量化回测 - 缓存管理模块

功能：
1. 回测结果缓存（Redis，TTL 7天）
2. 历史记录管理（前10条）
3. 参数哈希计算
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any


class BacktestCache:
    """回测结果缓存管理器"""
    
    CACHE_PREFIX = "backtest:v1"
    HISTORY_PREFIX = "backtest:history"
    CACHE_TTL_DAYS = 7
    MAX_HISTORY = 10
    
    def __init__(self, redis_client):
        """
        初始化缓存管理器
        
        Args:
            redis_client: Redis 客户端实例
        """
        self.redis = redis_client
    
    def _compute_hash(self, params: Dict) -> str:
        """
        计算参数哈希值
        
        对参数进行排序后序列化，确保相同参数产生相同hash
        
        Args:
            params: 回测参数字典
            
        Returns:
            16位十六进制哈希字符串
        """
        # 只包含影响结果的参数
        hash_params = {
            'conditions': params.get('conditions', []),
            'take_profit_pct': params.get('take_profit_pct', 0.5),
            'stop_loss_pct': params.get('stop_loss_pct', 0.3),
            'window_minutes': params.get('window_minutes', 5),
            'dedup': params.get('dedup', 'first_per_minute'),
            'time_start': params.get('time_start', '09:30:00'),
            'time_end': params.get('time_end', '15:00:00'),
            'price_offset': params.get('price_offset', 0.0),
            'offset_mode': params.get('offset_mode', 'fixed'),
            'date_start': params.get('date_start'),
            'date_end': params.get('date_end'),
            'timeline_mode': params.get('timeline_mode', False),
            'initial_capital': params.get('initial_capital', 1000000),
            'return_calc_method': params.get('return_calc_method', 'compound')
        }
        
        # 排序后序列化
        normalized = json.dumps(hash_params, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
    
    def get(self, params: Dict) -> Optional[Dict]:
        """
        获取缓存的回测结果
        
        Args:
            params: 回测参数
            
        Returns:
            缓存数据或 None
        """
        hash_key = self._compute_hash(params)
        cache_key = f"{self.CACHE_PREFIX}:{hash_key}"
        
        try:
            cached = self.redis.get(cache_key)
            if cached:
                if isinstance(cached, bytes):
                    cached = cached.decode('utf-8')
                return json.loads(cached)
        except Exception as e:
            print(f"[BacktestCache] Get error: {e}")
        
        return None
    
    def set(self, params: Dict, result: Dict) -> str:
        """
        设置缓存并更新历史记录
        
        Args:
            params: 回测参数
            result: 回测结果
            
        Returns:
            缓存哈希值
        """
        hash_key = self._compute_hash(params)
        cache_key = f"{self.CACHE_PREFIX}:{hash_key}"
        
        data = {
            "meta": {
                "created_at": datetime.now().isoformat(),
                "hash": hash_key,
                "params": params
            },
            "result": result
        }
        
        try:
            # 写入缓存（带TTL）
            self.redis.setex(
                cache_key,
                timedelta(days=self.CACHE_TTL_DAYS),
                json.dumps(data, ensure_ascii=False)
            )
            
            # 更新历史记录
            self._update_history(hash_key, params, result)
            
        except Exception as e:
            print(f"[BacktestCache] Set error: {e}")
        
        return hash_key
    
    def _update_history(self, hash_key: str, params: Dict, result: Dict):
        """
        更新历史记录列表
        
        Args:
            hash_key: 缓存哈希
            params: 回测参数
            result: 回测结果
        """
        # 简化：使用固定user_id，实际应用应传入
        history_key = f"{self.HISTORY_PREFIX}:default"
        
        history_item = {
            "timestamp": datetime.now().isoformat(),
            "hash": hash_key,
            "params": params,
            "summary_preview": self._extract_preview(result)
        }
        
        try:
            # LPUSH 到列表头部（最新在前）
            self.redis.lpush(history_key, json.dumps(history_item, ensure_ascii=False))
            
            # 限制长度
            self.redis.ltrim(history_key, 0, self.MAX_HISTORY - 1)
            
            # 设置TTL
            self.redis.expire(history_key, timedelta(days=self.CACHE_TTL_DAYS))
            
        except Exception as e:
            print(f"[BacktestCache] Update history error: {e}")
    
    def _extract_preview(self, result: Dict) -> Dict:
        """
        从结果中提取摘要信息
        
        Args:
            result: 回测结果
            
        Returns:
            摘要字典
        """
        summary = result.get("summary", {})
        return {
            "date_start": summary.get("date_start"),
            "date_end": summary.get("date_end"),
            "trade_days": summary.get("trade_days"),
            "total_signals": summary.get("total_signals"),
            "total_return_pct": summary.get("total_return_pct")
        }
    
    def get_history(self, user_id: str = "default") -> List[Dict]:
        """
        获取历史记录列表
        
        Args:
            user_id: 用户标识
            
        Returns:
            历史记录列表
        """
        history_key = f"{self.HISTORY_PREFIX}:{user_id}"
        
        try:
            items = self.redis.lrange(history_key, 0, -1)
            result = []
            for item in items:
                if isinstance(item, bytes):
                    item = item.decode('utf-8')
                result.append(json.loads(item))
            return result
        except Exception as e:
            print(f"[BacktestCache] Get history error: {e}")
            return []
    
    def get_by_hash(self, hash_key: str) -> Optional[Dict]:
        """
        通过哈希值获取缓存
        
        Args:
            hash_key: 缓存哈希
            
        Returns:
            缓存数据或 None
        """
        cache_key = f"{self.CACHE_PREFIX}:{hash_key}"
        
        try:
            cached = self.redis.get(cache_key)
            if cached:
                if isinstance(cached, bytes):
                    cached = cached.decode('utf-8')
                return json.loads(cached)
        except Exception as e:
            print(f"[BacktestCache] Get by hash error: {e}")
        
        return None
    
    def delete_history(self, hash_key: str, user_id: str = "default"):
        """
        删除历史记录
        
        Args:
            hash_key: 要删除的缓存哈希
            user_id: 用户标识
        """
        history_key = f"{self.HISTORY_PREFIX}:{user_id}"
        
        try:
            # 获取所有历史
            items = self.redis.lrange(history_key, 0, -1)
            
            # 过滤掉要删除的
            new_items = []
            for item in items:
                if isinstance(item, bytes):
                    item = item.decode('utf-8')
                item_data = json.loads(item)
                if item_data.get("hash") != hash_key:
                    new_items.append(item)
            
            # 重新写入
            self.redis.delete(history_key)
            if new_items:
                # 反转顺序（因为LPUSH，新的在前）
                for item in reversed(new_items):
                    self.redis.rpush(history_key, item)
            
            # 删除缓存
            cache_key = f"{self.CACHE_PREFIX}:{hash_key}"
            self.redis.delete(cache_key)
            
        except Exception as e:
            print(f"[BacktestCache] Delete history error: {e}")
    
    def clear_all(self, user_id: str = "default"):
        """
        清空所有缓存和历史（谨慎使用）
        
        Args:
            user_id: 用户标识
        """
        history_key = f"{self.HISTORY_PREFIX}:{user_id}"
        
        try:
            # 获取所有历史
            items = self.redis.lrange(history_key, 0, -1)
            
            # 删除所有缓存
            for item in items:
                if isinstance(item, bytes):
                    item = item.decode('utf-8')
                item_data = json.loads(item)
                hash_key = item_data.get("hash")
                if hash_key:
                    cache_key = f"{self.CACHE_PREFIX}:{hash_key}"
                    self.redis.delete(cache_key)
            
            # 删除历史列表
            self.redis.delete(history_key)
            
        except Exception as e:
            print(f"[BacktestCache] Clear all error: {e}")
