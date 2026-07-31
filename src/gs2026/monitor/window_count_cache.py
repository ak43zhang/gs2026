"""
区间次数缓存管理模块
- 默认内存缓存，高性能
- 宕机恢复：从数据库重建
- 可独立删除，不影响主体代码
"""

from datetime import datetime
import threading
from typing import Dict, Tuple, Optional

# 缓存结构：{(date, window_start, code): count}
_window_count_cache: Dict[Tuple[str, str, str], int] = {}
_cache_lock = threading.Lock()
_last_window_start: Optional[str] = None
_last_date: Optional[str] = None


def get_window_count(code: str, date: str, current_time_str: str, 
                     table_name: str = None, engine = None) -> int:
    """
    获取并递增区间次数
    
    Args:
        code: 股票/债券代码
        date: 日期 YYYYMMDD
        current_time_str: 当前时间 HH:MM:SS
        table_name: 数据库表名（宕机恢复用，可选）
        engine: 数据库引擎（宕机恢复用，可选）
    
    Returns:
        递增后的次数（本次是第几次）
    """
    global _last_window_start, _last_date
    
    # 计算当前区间起始
    window_start = _calculate_window_start(current_time_str)
    
    # 跨区间检测
    if _is_window_changed(date, window_start):
        _clear_old_window_cache(date, window_start)
    
    _last_window_start = window_start
    _last_date = date
    
    key = (date, window_start, code)
    
    with _cache_lock:
        # 缓存命中
        if key in _window_count_cache:
            _window_count_cache[key] += 1
            return _window_count_cache[key]
        
        # 缓存未命中：可能宕机恢复，尝试从数据库重建
        count = _rebuild_from_db(code, date, window_start, current_time_str, 
                                  table_name, engine)
        _window_count_cache[key] = count + 1
        return _window_count_cache[key]


def _calculate_window_start(time_str: str) -> str:
    """计算10分钟区间起始"""
    hh, mm, _ = time_str.split(':')
    hour, minute = int(hh), int(mm)
    window_start = (minute // 10) * 10
    return f"{hour:02d}:{window_start:02d}:00"


def _is_window_changed(date: str, window_start: str) -> bool:
    """检测是否跨区间"""
    return (_last_date and _last_date == date and 
            _last_window_start and _last_window_start != window_start)


def _clear_old_window_cache(date: str, current_window: str):
    """清理旧区间缓存"""
    global _window_count_cache
    keys_to_remove = [
        k for k in list(_window_count_cache.keys())
        if k[0] == date and k[1] != current_window
    ]
    for k in keys_to_remove:
        del _window_count_cache[k]


def _rebuild_from_db(code: str, date: str, window_start: str, 
                     current_time: str, table_name: str, engine) -> int:
    """
    从数据库重建缓存（宕机恢复场景）
    无字段或查询失败时返回0
    """
    if not table_name or not engine:
        return 0
    
    try:
        # 查询本区间内该代码已出现次数
        query = f"""
            SELECT COUNT(*) as cnt 
            FROM {table_name} 
            WHERE code = '{code}' 
            AND time >= '{window_start}' 
            AND time < '{current_time}'
        """
        with engine.connect() as conn:
            result = conn.execute(query).fetchone()
            return result[0] if result else 0
    except Exception:
        # 字段不存在或查询失败，返回0
        return 0


def get_current_count(code: str, date: str, time_str: str) -> int:
    """获取当前次数（不递增，用于查询）"""
    window_start = _calculate_window_start(time_str)
    key = (date, window_start, code)
    with _cache_lock:
        return _window_count_cache.get(key, 0)
