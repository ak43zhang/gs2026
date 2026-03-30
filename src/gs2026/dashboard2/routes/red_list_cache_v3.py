"""
股市红名单 Redis 缓存管理 V3（简化版）
直接使用 mysql2redis_generate_dict 生成字典
"""
from datetime import datetime
from typing import Set, Optional
from gs2026.utils import redis_util, log_util

logger = log_util.setup_logger(__file__)

REDIS_KEY = "dict:red_list"


def update_red_list_cache() -> dict:
    """
    更新红名单缓存
    查询 buy_date = 今天的股票代码
    """
    today = datetime.now()
    today_str = today.strftime("%Y%m%d")
    date_sql = today.strftime("%Y-%m-%d")
    
    try:
        where_str = f"buy_date='{date_sql}'"
        redis_util.mysql2redis_generate_dict("red_list", "code", where_str)
        
        # 获取缓存数量
        df = redis_util.get_dict("red_list")
        count = len(df) if df is not None else 0
        
        logger.info(f"红名单缓存更新成功: {count} 只, 日期: {today_str}")
        return {
            "success": True,
            "date": today_str,
            "count": count
        }
    except Exception as e:
        logger.error(f"红名单缓存更新失败: {e}")
        return {"success": False, "error": str(e)}


def get_red_list() -> Set[str]:
    """获取今日红名单股票代码集合"""
    try:
        df = redis_util.get_dict("red_list")
        if df is not None and "code" in df.columns:
            return set(df["code"].astype(str).tolist())
        return set()
    except Exception as e:
        logger.error(f"获取红名单失败: {e}")
        return set()


def is_in_red_list(code: str) -> bool:
    """检查股票是否在红名单中"""
    return str(code) in get_red_list()
