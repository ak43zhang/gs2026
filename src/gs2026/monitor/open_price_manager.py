"""
开盘价管理模块 - 单表设计

表结构: market_open_prices
- id: 主键
- trade_date: 交易日期 YYYYMMDD
- stock_code: 股票代码
- open_price: 开盘价
- created_at: 创建时间
- updated_at: 更新时间

索引:
- PRIMARY: id
- UNIQUE: (trade_date, stock_code) - 防止重复
- INDEX: trade_date - 按日期查询
- INDEX: stock_code - 按代码查询
"""

import pandas as pd
import threading
from datetime import datetime
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

# 配置
FREEZE_AFTER_TICKS = 10  # 10个tick后冻结

# 全局状态（单日）
_tick_count: int = 0
_is_frozen: bool = False
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1)

# 内存缓存
_open_prices: Dict[str, float] = {}
_is_initialized: bool = False
_current_date: str = ""


def init_open_prices(date_str: str) -> bool:
    """
    初始化开盘价（启动时调用一次）
    
    Returns:
        True: 已冻结（从缓存加载）
        False: 进入采集模式
    """
    global _is_initialized, _is_frozen, _tick_count, _current_date
    
    with _lock:
        if _is_initialized and _current_date == date_str:
            return _is_frozen
        
        _is_initialized = True
        _current_date = date_str
        _tick_count = 0
        _is_frozen = False
        _open_prices.clear()
    
    # 尝试加载已有数据
    if _load_from_redis(date_str) or _load_from_mysql(date_str):
        with _lock:
            _is_frozen = True
        logger.info(f"[开盘价] 从缓存加载并冻结: {len(_open_prices)}条")
        return True
    
    logger.info("[开盘价] 进入采集模式，等待前10个tick...")
    return False


def ensure_open_prices(df_now: pd.DataFrame, time_str: str, date_str: str = None) -> pd.DataFrame:
    """
    确保开盘价（每tick调用）
    
    Args:
        df_now: 当前tick数据
        time_str: 时间 HH:MM:SS
        date_str: 日期 YYYYMMDD（可选，默认当日）
    
    Returns:
        添加了 open_price 列的 df
    """
    global _tick_count, _is_frozen
    
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    
    # 首次初始化
    if not _is_initialized or _current_date != date_str:
        init_open_prices(date_str)
    
    with _lock:
        # 冻结模式：只读查询
        if _is_frozen:
            df_now['open_price'] = df_now['stock_code'].map(_open_prices)
            # 未找到开盘价的填充 NaN
            df_now['open_price'] = df_now['open_price'].fillna(0)
            return df_now
        
        # 采集模式
        _tick_count += 1
        current_tick = _tick_count
        
        # tick 1: 初始化
        if current_tick == 1:
            _open_prices.clear()
            _open_prices.update(dict(zip(
                df_now['stock_code'].astype(str),
                df_now['price'].astype(float)
            )))
            logger.info(f"[开盘价] tick {current_tick}: 初始化 {len(_open_prices)}条 @ {time_str}")
        
        # tick 2-10: 补全
        else:
            existing_codes = set(_open_prices.keys())
            new_codes = []
            
            for _, row in df_now.iterrows():
                code = str(row['stock_code'])
                if code not in existing_codes:
                    _open_prices[code] = float(row['price'])
                    new_codes.append(code)
            
            if new_codes:
                logger.info(f"[开盘价] tick {current_tick}: 补全 {len(new_codes)}条，累计 {len(_open_prices)}条")
        
        # 检查冻结
        should_freeze = current_tick >= FREEZE_AFTER_TICKS
        should_save = should_freeze or (current_tick in [3, 6, 10])
        
        if should_freeze:
            _is_frozen = True
            logger.info(f"[开盘价] tick {current_tick}: 已冻结（共{len(_open_prices)}条）")
        
        prices_to_save = dict(_open_prices) if should_save else None
        is_final = should_freeze
    
    # 异步保存（锁外）
    if prices_to_save:
        _executor.submit(_save_prices, date_str, prices_to_save, is_final)
    
    # 映射结果
    df_now['open_price'] = df_now['stock_code'].map(_open_prices)
    
    # 采集期缺失用当前价
    missing = df_now['open_price'].isna()
    if missing.any() and not _is_frozen:
        df_now.loc[missing, 'open_price'] = df_now.loc[missing, 'price']
    
    return df_now


def _save_prices(date_str: str, prices: Dict[str, float], is_final: bool):
    """保存价格"""
    try:
        _save_to_redis(date_str, prices)
        if is_final:
            _save_to_mysql(date_str, prices)
            logger.info(f"[开盘价] 最终持久化完成: {len(prices)}条")
    except Exception as e:
        logger.warning(f"[开盘价] 保存失败: {e}")


def _save_to_redis(date_str: str, prices: Dict[str, float]):
    """批量保存到Redis"""
    try:
        from gs2026.utils import redis_util
        client = redis_util._get_redis_client()
        
        mapping = {k: str(v) for k, v in prices.items()}
        client.hset(f"market:open_prices:{date_str}", mapping=mapping)
        client.expire(f"market:open_prices:{date_str}", 24 * 3600)
        
    except Exception as e:
        logger.debug(f"[开盘价] Redis保存失败: {e}")


def _save_to_mysql(date_str: str, prices: Dict[str, float]):
    """批量保存到MySQL（单表设计）"""
    try:
        from gs2026.monitor.monitor_stock import engine
        from sqlalchemy import text
        
        with engine.begin() as conn:
            # 分批插入/更新
            items = list(prices.items())
            for i in range(0, len(items), 2000):
                batch = items[i:i+2000]
                
                # 使用 INSERT ... ON DUPLICATE KEY UPDATE
                values_list = []
                for code, price in batch:
                    values_list.append(f"('{date_str}', '{code}', {price})")
                
                values = ",".join(values_list)
                
                sql = f"""
                    INSERT INTO market_open_prices 
                        (trade_date, stock_code, open_price)
                    VALUES {values}
                    ON DUPLICATE KEY UPDATE 
                        open_price = VALUES(open_price),
                        updated_at = CURRENT_TIMESTAMP
                """
                
                conn.execute(text(sql))
                
    except Exception as e:
        logger.warning(f"[开盘价] MySQL保存失败: {e}")


def _load_from_redis(date_str: str) -> bool:
    """从Redis加载"""
    try:
        from gs2026.utils import redis_util
        client = redis_util._get_redis_client()
        
        data = client.hgetall(f"market:open_prices:{date_str}")
        if not data or len(data) < 1000:
            return False
        
        _open_prices.clear()
        _open_prices.update({
            k.decode() if isinstance(k, bytes) else k: float(v)
            for k, v in data.items()
        })
        return True
        
    except Exception as e:
        logger.debug(f"[开盘价] Redis加载失败: {e}")
        return False


def _load_from_mysql(date_str: str) -> bool:
    """从MySQL加载（单表设计）"""
    try:
        from gs2026.monitor.monitor_stock import engine
        
        df = pd.read_sql(
            f"SELECT stock_code, open_price FROM market_open_prices WHERE trade_date = '{date_str}'",
            engine
        )
        
        if len(df) < 1000:
            return False
        
        _open_prices.clear()
        _open_prices.update(dict(zip(
            df['stock_code'].astype(str),
            df['open_price'].astype(float)
        )))
        return True
        
    except Exception as e:
        logger.debug(f"[开盘价] MySQL加载失败: {e}")
        return False


def get_open_price(code: str) -> Optional[float]:
    """获取单只股票开盘价"""
    return _open_prices.get(code)


def is_frozen() -> bool:
    """检查是否已冻结"""
    return _is_frozen


def get_stats() -> dict:
    """获取统计"""
    return {
        "tick_count": _tick_count,
        "is_frozen": _is_frozen,
        "total_prices": len(_open_prices),
        "date": _current_date,
    }


def reset():
    """重置状态（用于测试）"""
    global _is_initialized, _is_frozen, _tick_count, _current_date
    with _lock:
        _is_initialized = False
        _is_frozen = False
        _tick_count = 0
        _current_date = ""
        _open_prices.clear()
