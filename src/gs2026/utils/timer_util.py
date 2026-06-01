"""定时执行工具模块——独立于代理池，可安全导入。

提供 check_time_and_execute 函数，用于在指定时间到达后执行回调函数。
此模块不依赖任何代理池或 DeepSeek 相关模块，适用于纯数据采集场景。
"""

import time
from datetime import datetime
from typing import Any, Callable

from loguru import logger


def check_time_and_execute(
        target_date: datetime,
        check_interval: int,
        execute_func: Callable[..., Any],
        *func_args: Any,
        **func_kwargs: Any
) -> Any:
    """定时检查并在目标时间到达后执行指定函数。

    以 check_interval 为间隔循环检查当前时间，当当前时间
    超过 target_date 时执行 execute_func 并返回其结果。

    Args:
        target_date: 目标执行时间。
        check_interval: 检查间隔（秒）。
        execute_func: 需要执行的回调函数。
        *func_args: 传递给 execute_func 的位置参数。
        **func_kwargs: 传递给 execute_func 的关键字参数。

    Returns:
        execute_func 的返回值。

    Example::

        result = check_time_and_execute(
            target_date=datetime(2026, 3, 20, 9, 30),
            check_interval=60,
            execute_func=my_collect_func,
            '2026-03-20', '2026-03-20'
        )
    """
    logger.info(f"目标时间: {target_date.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("开始循环检查，每隔1分钟检查一次...")

    while True:
        current_time: datetime = datetime.now()

        if current_time > target_date:
            # 目标时间已到，执行任务
            logger.info(f"\n✅ 时间已到！当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"开始执行函数: {execute_func.__name__}...")

            # 执行传入的函数
            result = execute_func(*func_args, **func_kwargs)

            logger.info("任务执行完成，程序继续运行...")
            return result

        else:
            # 计算剩余等待时间并周期性输出日志
            remaining = target_date - current_time
            days: int = remaining.days
            seconds: int = remaining.seconds
            hours: int = seconds // 3600
            minutes: int = (seconds % 3600) // 60

            current_minute: int = current_time.minute
            # 每 10 分钟或剩余不足 1 小时时输出等待状态
            if current_minute % 10 == 0 or remaining.total_seconds() < 3600:
                logger.info(f"当前时间: {current_time.strftime('%H:%M:%S')}, "
                            f"剩余: {days}天{hours}小时{minutes}分钟")

        time.sleep(check_interval)
