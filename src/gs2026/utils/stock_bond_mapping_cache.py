"""
股票-债券-行业映射 Redis 缓存工具
"""

import json
from typing import Optional, Dict, List
from datetime import datetime
import pandas as pd

from gs2026.utils import redis_util, log_util
from gs2026.monitor.stock_bond_industry_mapping import get_stock_bond_industry_mapping

logger = log_util.setup_logger(__file__)

# Redis Key 常量
REDIS_KEY_PREFIX = "stock_bond_mapping"
REDIS_KEY_LATEST_DATE = f"{REDIS_KEY_PREFIX}:latest_date"
REDIS_KEY_META = f"{REDIS_KEY_PREFIX}:meta"


class StockBondMappingCache:
    """股票-债券-行业映射缓存管理器"""
    
    def __init__(self, redis_client=None):
        if redis_client:
            self.redis = redis_client
        else:
            # 确保Redis已初始化
            if redis_util._redis_client is None:
                redis_util.init_redis()
            self.redis = redis_util._redis_client
    
    def _get_mapping_key(self, date: str) -> str:
        """获取指定日期的映射 Key"""
        return f"{REDIS_KEY_PREFIX}:{date}"
    
    def update_mapping(
        self,
        min_bond_price: float = 120.0,
        max_bond_price: float = 250.0,
        redemption_days_threshold: int = 30,
        force: bool = False
    ) -> Dict:
        """
        更新映射缓存
        
        Args:
            min_bond_price: 最小债券价格
            max_bond_price: 最大债券价格
            redemption_days_threshold: 赎回日期阈值
            force: 是否强制更新（即使已存在）
        
        Returns:
            更新结果信息
        """
        today = datetime.now().strftime('%Y-%m-%d')
        mapping_key = self._get_mapping_key(today)
        
        # 检查是否已存在
        if not force and self.redis.exists(mapping_key):
            logger.info(f"映射缓存已存在: {mapping_key}")
            return {
                "success": True,
                "message": "缓存已存在，跳过更新",
                "date": today,
                "exists": True
            }
        
        try:
            # 生成映射数据
            logger.info("开始生成股票-债券-行业映射...")
            mapping_df = get_stock_bond_industry_mapping(
                min_bond_price=min_bond_price,
                max_bond_price=max_bond_price,
                redemption_days_threshold=redemption_days_threshold
            )
            
            total_count = len(mapping_df)
            logger.info(f"生成映射记录: {total_count} 条")
            
            # 使用 Pipeline 批量写入
            pipe = self.redis.pipeline()
            
            for _, row in mapping_df.iterrows():
                stock_code = str(row['stock_code'])
                data = {
                    "stock_code": stock_code,
                    "stock_name": str(row['short_name']) if pd.notna(row['short_name']) else "",
                    "bond_code": str(row['bond_code']) if pd.notna(row['bond_code']) else "",
                    "bond_name": str(row['bond_name']) if pd.notna(row['bond_name']) else "",
                    "industry_name": str(row['industry_name']) if pd.notna(row['industry_name']) else ""
                }
                pipe.hset(mapping_key, stock_code, json.dumps(data))
            
            # 设置 7 天过期
            pipe.expire(mapping_key, 7 * 24 * 3600)
            
            # 更新最新日期标记
            pipe.set(REDIS_KEY_LATEST_DATE, today)
            
            # 更新元数据
            meta = {
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "total_count": total_count,
                "price_range": [min_bond_price, max_bond_price],
                "bond_daily_date": self._get_bond_daily_date(),
                "version": "1.0"
            }
            pipe.set(REDIS_KEY_META, json.dumps(meta))
            
            # 执行 Pipeline
            pipe.execute()
            
            logger.info(f"映射缓存更新成功: {mapping_key}, 共 {total_count} 条")
            
            return {
                "success": True,
                "message": "缓存更新成功",
                "date": today,
                "total_count": total_count,
                "exists": False
            }
            
        except Exception as e:
            logger.error(f"更新映射缓存失败: {e}")
            return {
                "success": False,
                "message": f"更新失败: {str(e)}",
                "date": today,
                "exists": False
            }
    
    def get_mapping(self, stock_code: str, date: str = None) -> Optional[Dict]:
        """
        获取单只股票映射
        
        Args:
            stock_code: 股票代码
            date: 指定日期，默认使用最新日期
        
        Returns:
            映射数据字典，不存在返回 None
        """
        if date is None:
            date = self.get_latest_date()
        
        if date is None:
            return None
        
        mapping_key = self._get_mapping_key(date)
        data = self.redis.hget(mapping_key, str(stock_code))
        
        if data:
            return json.loads(data)
        return None
    
    def get_all_mapping(self, date: str = None) -> Dict[str, Dict]:
        """
        获取全部映射
        
        Args:
            date: 指定日期，默认使用最新日期
        
        Returns:
            {stock_code: mapping_data} 字典
        """
        if date is None:
            date = self.get_latest_date()
        
        if date is None:
            return {}
        
        mapping_key = self._get_mapping_key(date)
        all_data = self.redis.hgetall(mapping_key)
        
        return {
            k: json.loads(v) for k, v in all_data.items()
        }
    
    def get_latest_date(self) -> Optional[str]:
        """获取最新映射日期"""
        date = self.redis.get(REDIS_KEY_LATEST_DATE)
        return date.decode('utf-8') if date else None
    
    def get_meta(self) -> Optional[Dict]:
        """获取映射元数据"""
        meta = self.redis.get(REDIS_KEY_META)
        if meta:
            return json.loads(meta)
        return None
    
    def is_cache_valid(self) -> bool:
        """
        检查缓存是否有效（是否为今天）
        
        Returns:
            True: 缓存有效
            False: 缓存不存在或过期
        """
        latest_date = self.get_latest_date()
        if latest_date is None:
            return False
        
        today = datetime.now().strftime('%Y-%m-%d')
        return latest_date == today
    
    def ensure_cache(self, **kwargs) -> bool:
        """
        确保缓存存在（不存在则自动创建）
        
        Returns:
            True: 缓存可用
            False: 创建失败
        """
        if self.is_cache_valid():
            return True
        
        result = self.update_mapping(**kwargs)
        return result["success"]
    
    def _get_bond_daily_date(self) -> str:
        """获取债券日行情最新日期（从数据库）"""
        try:
            from sqlalchemy import create_engine, text
            from gs2026.utils import config_util
            
            url = config_util.get_config("common.url")
            engine = create_engine(url, pool_recycle=3600)
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT MAX(date) FROM data_bond_daily"))
                date = result.fetchone()[0]
                return str(date) if date else ""
        except Exception as e:
            logger.warning(f"获取债券日行情日期失败: {e}")
            return ""


# 全局缓存实例
cache = None

def get_cache() -> StockBondMappingCache:
    """获取全局缓存实例（单例模式）"""
    global cache
    if cache is None:
        cache = StockBondMappingCache()
    return cache
