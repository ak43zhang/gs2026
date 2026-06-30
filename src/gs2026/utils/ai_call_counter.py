"""AI调用次数限制模块（MySQL版本）

非嵌入式设计：
- 接入：在AI调用前加 if not check_and_increment("process_name"): return None
- 移除：删除上述判断即可

规则：
- ai_call_limit表中无此进程配置 → 永久模式，直接通过
- max_calls=0 → 永久模式，直接通过
- enabled=0 → 限制禁用，直接通过
- 数据库异常 → 降级放行，记录警告日志
"""

import threading
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy import create_engine, text

from gs2026.utils import config_util

_lock = threading.Lock()
_engine = None


def _get_engine():
    """延迟创建数据库引擎（单例）"""
    global _engine
    if _engine is None:
        url = config_util.get_config("common.url")
        _engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    return _engine


def check_and_increment(process_name: str) -> bool:
    """
    检查并增加调用计数（AI调用前必须调用此函数）

    Args:
        process_name: 进程名（对应ai_call_limit表的process_name）

    Returns:
        True: 可以继续调用AI
        False: 已达到上限，需要停止
    """
    with _lock:
        try:
            engine = _get_engine()
            today = date.today().strftime('%Y-%m-%d')

            with engine.begin() as conn:
                # 1. 查询上限配置
                result = conn.execute(text(
                    "SELECT max_calls, enabled FROM ai_call_limit WHERE process_name = :name"
                ), {"name": process_name}).fetchone()

                # 无配置记录 → 永久模式
                if result is None:
                    return True

                max_calls, enabled = result[0], result[1]

                # 限制禁用 → 直接通过
                if not enabled:
                    return True

                # max_calls=0 → 永久模式
                if max_calls == 0:
                    return True

                # 2. 原子操作：增加计数器
                conn.execute(text("""
                    INSERT INTO ai_call_counter (process_name, call_date, call_count, last_call_time)
                    VALUES (:name, :today, 1, NOW())
                    ON DUPLICATE KEY UPDATE
                        call_count = call_count + 1,
                        last_call_time = NOW()
                """), {"name": process_name, "today": today})

                # 3. 查询当前计数
                count_result = conn.execute(text(
                    "SELECT call_count FROM ai_call_counter WHERE process_name = :name AND call_date = :today"
                ), {"name": process_name, "today": today}).fetchone()

                current_count = count_result[0] if count_result else 0

                # 4. 检查是否超过上限
                if current_count > max_calls:
                    logger.warning(
                        f"[AI调用限制] {process_name} 已达上限: {current_count}/{max_calls}，停止调用"
                    )
                    return False

                # 5. 接近上限时警告（>=90%）
                if current_count >= max_calls * 0.9:
                    remaining = max_calls - current_count
                    logger.warning(
                        f"[AI调用限制] {process_name} 即将耗尽: {current_count}/{max_calls}，剩余{remaining}次"
                    )

                return True

        except Exception as e:
            # 数据库异常 → 降级放行
            logger.warning(f"[AI调用限制] 数据库异常，降级放行: {e}")
            return True


def get_status(process_name: str) -> dict:
    """
    获取指定进程的调用状态

    Returns:
        {"process_name": str, "call_count": int, "max_calls": int, "remaining": int, "status": str}
    """
    try:
        engine = _get_engine()
        today = date.today().strftime('%Y-%m-%d')

        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    l.process_name,
                    COALESCE(c.call_count, 0) as call_count,
                    l.max_calls,
                    l.enabled,
                    c.last_call_time
                FROM ai_call_limit l
                LEFT JOIN ai_call_counter c ON l.process_name = c.process_name AND c.call_date = :today
                WHERE l.process_name = :name
            """), {"name": process_name, "today": today}).fetchone()

            if result is None:
                return {"process_name": process_name, "call_count": 0, "max_calls": 0,
                        "remaining": -1, "status": "未配置"}

            call_count = result[1]
            max_calls = result[2]
            enabled = result[3]

            if not enabled:
                status = "已禁用"
                remaining = -1
            elif max_calls == 0:
                status = "永久"
                remaining = -1
            elif call_count >= max_calls:
                status = "已耗尽"
                remaining = 0
            elif call_count >= max_calls * 0.9:
                status = "即将耗尽"
                remaining = max_calls - call_count
            else:
                status = "正常"
                remaining = max_calls - call_count

            return {
                "process_name": process_name,
                "call_count": call_count,
                "max_calls": max_calls,
                "remaining": remaining,
                "status": status
            }

    except Exception as e:
        logger.warning(f"[AI调用限制] 查询状态异常: {e}")
        return {"process_name": process_name, "call_count": 0, "max_calls": 0,
                "remaining": -1, "status": "查询异常"}


def set_limit(process_name: str, max_calls: int, description: str = ''):
    """设置指定进程的上限（0=永久）"""
    try:
        engine = _get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ai_call_limit (process_name, max_calls, description)
                VALUES (:name, :max_calls, :desc)
                ON DUPLICATE KEY UPDATE max_calls = :max_calls, description = :desc
            """), {"name": process_name, "max_calls": max_calls, "desc": description})
        logger.info(f"[AI调用限制] 设置 {process_name} 上限: {max_calls if max_calls > 0 else '永久'}")
    except Exception as e:
        logger.error(f"[AI调用限制] 设置上限异常: {e}")


def reset_counter(process_name: str = None):
    """重置指定进程今日的计数器（process_name=None则重置所有）"""
    try:
        engine = _get_engine()
        today = date.today().strftime('%Y-%m-%d')
        with engine.begin() as conn:
            if process_name:
                conn.execute(text(
                    "DELETE FROM ai_call_counter WHERE process_name = :name AND call_date = :today"
                ), {"name": process_name, "today": today})
                logger.info(f"[AI调用限制] 已重置 {process_name} 今日计数器")
            else:
                conn.execute(text(
                    "DELETE FROM ai_call_counter WHERE call_date = :today"
                ), {"today": today})
                logger.info("[AI调用限制] 已重置所有进程今日计数器")
    except Exception as e:
        logger.error(f"[AI调用限制] 重置计数器异常: {e}")
