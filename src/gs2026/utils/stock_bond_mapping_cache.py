"""
股票-债券-行业映射 Redis 缓存工具（三层缓存策略）
"""

import json
import threading
import time
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
    """股票-债券-行业映射缓存管理器（三层缓存）"""
    
    def __init__(self, redis_client=None):
        if redis_client:
            self.redis = redis_client
        else:
            # 确保Redis已初始化
            if redis_util._redis_client is None:
                redis_util.init_redis()
            self.redis = redis_util._redis_client
        
        # 【新增】Layer 1: 内存缓存
        self._memory_cache: Dict[str, Dict] = {}
        self._memory_lock = threading.RLock()
        self._memory_ready = False
    
    def _get_mapping_key(self, date: str) -> str:
        """获取指定日期的映射 Key"""
        return f"{REDIS_KEY_PREFIX}:{date}"
    
    # ========== 【新增】Layer 1: 内存缓存方法 ==========
    
    def get_from_memory(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        从内存缓存获取（Layer 1，最快 O(1)）
        
        Returns:
            {stock_code: mapping_data}，未命中返回空值
        """
        with self._memory_lock:
            if not self._memory_ready:
                return {}
            return {code: self._memory_cache.get(code) for code in stock_codes}
    
    def update_memory(self, mappings: Dict[str, Dict]):
        """更新内存缓存"""
        with self._memory_lock:
            self._memory_cache = mappings
            self._memory_ready = True
            logger.info(f"内存缓存更新: {len(mappings)} 条")
    
    def is_memory_ready(self) -> bool:
        """检查内存缓存是否就绪"""
        with self._memory_lock:
            return self._memory_ready
    
    # ========== 【新增】Layer 3: 数据库直查兜底 ==========
    
    def get_from_db(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        从数据库直查映射（Layer 3，兜底，准确但慢）
        
        Returns:
            {stock_code: mapping_data}
        """
        if not stock_codes:
            return {}
        
        try:
            from sqlalchemy import create_engine, text
            from gs2026.utils import config_util
            
            url = config_util.get_config("common.url")
            engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
            
            # 构建 IN 语句
            codes_str = ','.join([f"'{c}'" for c in stock_codes])
            
            # 【优化】使用 JOIN 查询，单次获取所有映射
            sql = text(f"""
                SELECT 
                    s.stock_code,
                    s.stock_name,
                    sb.bond_code,
                    COALESCE(b.bond_name, '') as bond_name,
                    COALESCE(i.industry_name, '') as industry_name
                FROM (
                    SELECT DISTINCT stock_code, stock_name 
                    FROM monitor_bond_stock_mapping 
                    WHERE stock_code IN ({codes_str})
                ) s
                LEFT JOIN monitor_bond_stock_mapping sb ON s.stock_code = sb.stock_code
                LEFT JOIN monitor_bond_info b ON sb.bond_code = b.bond_code
                LEFT JOIN monitor_industry_info i ON sb.industry_code = i.industry_code
            """)
            
            with engine.connect() as conn:
                df = pd.read_sql(sql, conn)
                
                if df.empty:
                    return {}
                
                # 构建映射字典
                mappings = {}
                for _, row in df.iterrows():
                    code = str(row['stock_code'])
                    mappings[code] = {
                        'stock_code': code,
                        'stock_name': str(row['stock_name']) if pd.notna(row['stock_name']) else '',
                        'bond_code': str(row['bond_code']) if pd.notna(row['bond_code']) else '',
                        'bond_name': str(row['bond_name']) if pd.notna(row['bond_name']) else '',
                        'industry_name': str(row['industry_name']) if pd.notna(row['industry_name']) else ''
                    }
                
                logger.info(f"数据库直查映射: {len(mappings)} 条")
                return mappings
                
        except Exception as e:
            logger.error(f"数据库直查映射失败: {e}")
            return {}
    
    # ========== 【新增】智能查询（三层策略） ==========
    
    def get_mappings_smart(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        智能获取映射（三层缓存策略）
        
        优先级:
        1. Layer 1: 内存缓存（O(1)，最快）
        2. Layer 2: Redis 缓存（分布式）
        3. Layer 3: 数据库直查（兜底，准确）
        
        Returns:
            {stock_code: mapping_data}
        """
        if not stock_codes:
            return {}
        
        # 1. 尝试 Layer 1: 内存缓存
        mappings = self.get_from_memory(stock_codes)
        if mappings and all(mappings.values()):
            logger.debug(f"Layer 1 内存缓存命中: {len(mappings)} 条")
            return mappings
        
        # 2. 尝试 Layer 2: Redis 缓存
        if self.is_cache_valid():
            mappings = self.get_mappings_batch(stock_codes)
            if mappings:
                # 回填 Layer 1
                self.update_memory(mappings)
                logger.info(f"Layer 2 Redis 缓存命中: {len(mappings)} 条")
                return mappings
        
        # 3. 【兜底】Layer 3: 数据库直查
        logger.warning(f"Layer 3 数据库直查兜底: {len(stock_codes)} 条")
        mappings = self.get_from_db(stock_codes)
        
        # 触发异步缓存重建
        if not self.is_cache_valid():
            self.trigger_build_async()
        
        return mappings
    
    def trigger_build_async(self):
        """触发异步缓存重建"""
        def build():
            try:
                logger.info("异步重建缓存开始...")
                self.update_mapping(force=True)
                # 重建完成后回填内存缓存
                all_mappings = self.get_all_mapping()
                if all_mappings:
                    self.update_memory(all_mappings)
                    logger.info("异步重建缓存完成")
            except Exception as e:
                logger.error(f"异步重建缓存失败: {e}")
        
        thread = threading.Thread(target=build, daemon=True)
        thread.start()
        logger.info("已触发异步缓存重建")
    
    def update_mapping(
        self,
        min_bond_price: float = 120.0,
        max_bond_price: float = 250.0,
        redemption_days_threshold: int = 2,
        force: bool = True
    ) -> Dict:
        """
        更新映射缓存
        
        Args:
            min_bond_price: 最小债券价格
            max_bond_price: 最大债券价格
            redemption_days_threshold: 赎回日期阈值
            force: 是否强制更新（默认True，防止使用旧数据）
        
        Returns:
            更新结果信息
        """
        today = datetime.now().strftime('%Y-%m-%d')
        mapping_key = self._get_mapping_key(today)
        
        # 检查是否已存在（只有force=False时才跳过）
        if not force and self.redis.exists(mapping_key):
            logger.info(f"映射缓存已存在: {mapping_key}（跳过更新）")
            return {
                "success": True,
                "message": "缓存已存在，跳过更新",
                "date": today,
                "exists": True
            }
        
        # 强制更新模式（默认）：重新生成
        if self.redis.exists(mapping_key):
            logger.info("强制更新股票债券映射缓存（防止旧数据）")
        
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
    
    def get_mappings_batch(self, stock_codes: List[str], date: str = None) -> Dict[str, Dict]:
        """
        批量获取股票映射（使用Pipeline优化）
        
        Args:
            stock_codes: 股票代码列表
            date: 指定日期，默认使用最新日期
        
        Returns:
            {stock_code: mapping_data} 字典
        """
        if date is None:
            date = self.get_latest_date()
        
        if date is None or not stock_codes:
            return {}
        
        mapping_key = self._get_mapping_key(date)
        
        # 使用Pipeline批量查询
        pipe = self.redis.pipeline()
        for code in stock_codes:
            pipe.hget(mapping_key, str(code))
        
        results = pipe.execute()
        
        # 构建结果字典
        mappings = {}
        for code, data in zip(stock_codes, results):
            if data:
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                mappings[code] = json.loads(data)
        
        return mappings
    
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
