"""
通用任务运行器模块

提供后台线程运行、异常告警、优雅退出的统一封装。
避免每个分析脚本重复编写 threading + try/except + 邮件告警 的样板代码。

Usage:
    from gs2026.utils.task_runner import run_daemon_task

    # 方式1：简单运行
    run_daemon_task(target=time_task_do_cls, args=(10,))

    # 方式2：带数据库连接清理
    run_daemon_task(target=time_task_do_cls, args=(10,), cleanup=lambda: con.close())

    # 方式3：直接前台运行（不创建线程）
    run_daemon_task(target=time_task_do_cls, args=(10,), daemon=False)
"""

import os
import threading
import time
from typing import Callable, Optional, Tuple, Any

from loguru import logger

from gs2026.utils.email_util import EmailUtil


def run_daemon_task(
    target: Callable[..., Any],
    args: Tuple = (),
    kwargs: Optional[dict] = None,
    daemon: bool = True,
    cleanup: Optional[Callable[[], None]] = None,
    email_util: Optional[EmailUtil] = None,
    file_name: Optional[str] = None,
) -> None:
    """
    通用守护任务运行器

    将目标函数以后台守护线程方式运行，自动处理异常告警和资源清理。

    Args:
        target: 要执行的目标函数（注意：传函数引用，不要加括号调用）
        args: 目标函数的位置参数
        kwargs: 目标函数的关键字参数
        daemon: True=后台守护线程运行，False=前台直接运行
        cleanup: 可选的清理函数，在 finally 中调用（如关闭数据库连接）
        email_util: 邮件工具实例，用于异常告警。None 则使用默认实例
        file_name: 当前脚本文件名，用于告警邮件标识。None 则自动获取

    Raises:
        Exception: 当目标函数抛出非 KeyboardInterrupt 异常时，发送告警后重新抛出

    Note:
        常见错误：threading.Thread(target=func(args)) 会立即执行 func(args)，
        把返回值（通常是 None）作为 target。正确写法是 target=func, args=(args,)。
    """
    if kwargs is None:
        kwargs = {}

    if email_util is None:
        email_util = EmailUtil()

    if file_name is None:
        # 自动获取调用方的文件名
        import inspect
        frame = inspect.stack()[1]
        file_name = os.path.basename(frame.filename)

    start_time = time.time()

    try:
        if daemon:
            # 后台守护线程运行
            timer_thread = threading.Thread(
                target=target,
                args=args,
                kwargs=kwargs,
                name=f"daemon-{target.__name__}"
            )
            timer_thread.daemon = True
            timer_thread.start()

            logger.info(f"守护线程已启动: {target.__name__}")

            # 主线程保持运行
            while timer_thread.is_alive():
                timer_thread.join(timeout=1.0)
        else:
            # 前台直接运行
            logger.info(f"前台运行任务: {target.__name__}")
            target(*args, **kwargs)

    except KeyboardInterrupt:
        logger.warning(f"任务被用户中断: {target.__name__}")
        _send_alert(email_util, file_name, f"{file_name} 异常退出（用户中断）")

    except Exception as e:
        logger.exception(f"任务执行失败: {target.__name__} - {e}")
        _send_alert(email_util, file_name, f"{file_name} 执行异常: {str(e)}")
        raise

    finally:
        # 执行清理
        if cleanup is not None:
            try:
                cleanup()
                logger.info("资源清理完成")
            except Exception as e:
                logger.error(f"资源清理失败: {e}")

        elapsed = time.time() - start_time
        logger.info(f"任务总耗时: {elapsed:.2f} 秒")


def _send_alert(
    email_util: EmailUtil,
    file_name: str,
    error_content: str
) -> None:
    """
    发送异常告警邮件

    Args:
        email_util: 邮件工具实例
        file_name: 脚本文件名
        error_content: 错误内容描述
    """
    try:
        full_html = email_util.full_html_fun("异常告警", error_content)
        for receiver_email in email_util.get_email_list():
            email_util.email_send_html(receiver_email, "异常告警", full_html)
        logger.info("告警邮件已发送")
    except Exception as e:
        logger.error(f"告警邮件发送失败: {e}")
