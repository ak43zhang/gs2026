"""
股市红名单 Redis 缓存管理（优化版）
支持日期选择器切换日期
"""
from datetime import datetime
from typing import Set, Optional
from gs2026.utils import redis_util, log_util

logger = log_util.setup_logger(__file__)

REDIS_KEY = "dict:red_list"
REDIS_KEY_DATE = "dict:red_list_date"  # 存储当前缓存对应的日期


def clear_red_list_cache() -> bool:
    """
    清理红名单缓存
    删除 Redis 中的 dict:red_list 键
    """
    try:
        client = redis_util._get_redis_client()
        # 删除红名单数据
        client.delete(REDIS_KEY)
        # 删除日期标记
        client.delete(REDIS_KEY_DATE)
        logger.info("红名单缓存已清理")
        return True
    except Exception as e:
        logger.error(f"清理红名单缓存失败: {e}")
        return False


def update_red_list_cache(date_str: str = None) -> dict:
    """
    更新红名单缓存
    
    Args:
        date_str: 日期字符串 YYYYMMDD，默认使用今天
    
    Returns:
        更新结果字典
    """
    # 确定日期
    if date_str is None:
        target_date = datetime.now()
        date_str = target_date.strftime("%Y%m%d")
    else:
        # 解析 YYYYMMDD 格式
        target_date = datetime.strptime(date_str, "%Y%m%d")
    
    date_sql = target_date.strftime("%Y-%m-%d")
    
    try:
        # 先清理旧缓存
        clear_red_list_cache()
        
        # 查询指定日期的红名单
        where_str = f"WHERE buy_date='{date_sql}'"
        redis_util.mysql2redis_generate_dict("red_list", "code", where_str)
        
        # 保存当前缓存对应的日期
        client = redis_util._get_redis_client()
        client.set(REDIS_KEY_DATE, date_str)
        
        # 获取缓存数量
        df = redis_util.get_dict("red_list")
        count = len(df) if df is not None else 0
        
        logger.info(f"红名单缓存更新成功: {count} 只, 日期: {date_str}")
        return {
            "success": True,
            "date": date_str,
            "count": count
        }
    except Exception as e:
        logger.error(f"红名单缓存更新失败: {e}")
        return {"success": False, "error": str(e), "date": date_str}


def get_red_list_cache_date() -> Optional[str]:
    """
    获取当前红名单缓存对应的日期
    
    Returns:
        日期字符串 YYYYMMDD 或 None
    """
    try:
        client = redis_util._get_redis_client()
        date = client.get(REDIS_KEY_DATE)
        return date.decode('utf-8') if isinstance(date, bytes) else date
    except Exception as e:
        logger.error(f"获取红名单缓存日期失败: {e}")
        return None


def get_red_list() -> Set[str]:
    """
    获取红名单股票代码集合
    
    Returns:
        股票代码集合（6位字符串，补前导零）
    """
    try:
        df = redis_util.get_dict("red_list")
        if df is not None and "code" in df.columns:
            # 转换为字符串并补前导零到6位
            codes = df["code"].astype(str).str.zfill(6).tolist()
            return set(codes)
        return set()
    except Exception as e:
        logger.error(f"获取红名单失败: {e}")
        return set()


def is_in_red_list(code: str) -> bool:
    """
    检查股票是否在红名单中
    
    Args:
        code: 股票代码
    
    Returns:
        是否在红名单中
    """
    return str(code) in get_red_list()


def init_red_list_on_startup() -> dict:
    """
    启动时初始化红名单缓存
    先清理旧缓存，再更新为今天的红名单
    
    Returns:
        初始化结果
    """
    logger.info("启动时初始化红名单缓存...")
    # 先清理旧缓存
    clear_red_list_cache()
    # 更新为今天的红名单
    return update_red_list_cache()
