"""
装饰器工具模块

提供常用的装饰器功能，包括日志装饰器、重试装饰器、计时装饰器等。
"""

import functools
import os
import sys
import time
from typing import Callable, Any, Optional
import random
from functools import wraps
from pathlib import Path
from typing import Type, Tuple

from requests.exceptions import ChunkedEncodingError
from sqlalchemy.exc import OperationalError, DatabaseError, DataError
from urllib3.exceptions import ProtocolError

from loguru import logger

# 全局日志配置标志
_logger_configured = False
_default_log_dir: Optional[Path] = None


def _ensure_logger_configured():
    """确保日志已配置（只执行一次）"""
    global _logger_configured, _default_log_dir
    
    if _logger_configured:
        return
    
    # 获取日志目录
    try:
        from gs2026.utils.config_util import get_config
        log_dir = get_config("app.log_dir", "logs")
    except ImportError:
        # 如果 config_util 不可用，使用默认路径
        log_dir = "logs"
    
    # 转换为绝对路径
    if not os.path.isabs(log_dir):
        # 尝试找到项目根目录
        current = Path(__file__).absolute()
        for parent in current.parents:
            if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
                log_dir = parent / log_dir
                break
        else:
            log_dir = Path(log_dir)
    else:
        log_dir = Path(log_dir)
    
    # 创建日志目录
    log_dir.mkdir(parents=True, exist_ok=True)
    _default_log_dir = log_dir
    
    # 配置日志处理器
    logger.add(
        str(log_dir / "gs2026_{time:YYYYMMDD}.log"),
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        enqueue=True,
    )
    
    # 同时输出到控制台
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
        level="INFO",
    )
    
    _logger_configured = True
    logger.debug(f"日志已配置，目录: {log_dir}")


def log_decorator(
    log_level: str = "INFO",
    log_args: bool = True,
    log_result: bool = False,
    log_exception: bool = True,
    log_file: Optional[str] = None
):
    """
    日志装饰器

    自动记录函数调用、参数、返回值和异常信息。
    日志配置已集成，无需额外配置。
    
    Args:
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_args: 是否记录参数
        log_result: 是否记录返回值
        log_exception: 是否记录异常
        log_file: 指定日志文件名（可选，默认使用模块名）

    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        # 确保日志已配置
        _ensure_logger_configured()
        
        # 设置函数专属日志文件（可选）
        if log_file:
            _setup_function_logger(func, log_file)

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            func_name = func.__qualname__
            module_name = func.__module__

            # 记录函数调用
            if log_args:
                args_str = _format_args(args, kwargs)
                logger.log(
                    log_level,
                    f"[{module_name}] 调用 {func_name} | 参数: {args_str}"
                )
            else:
                logger.log(
                    log_level,
                    f"[{module_name}] 调用 {func_name}"
                )

            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time

                # 记录成功返回
                if log_result:
                    logger.log(
                        log_level,
                        f"[{module_name}] {func_name} 完成 | "
                        f"耗时: {elapsed:.3f}s | 返回: {_format_result(result)}"
                    )
                else:
                    logger.log(
                        log_level,
                        f"[{module_name}] {func_name} 完成 | 耗时: {elapsed:.3f}s"
                    )

                return result

            except Exception as e:
                elapsed = time.time() - start_time

                if log_exception:
                    logger.exception(
                        f"[{module_name}] {func_name} 异常 | "
                        f"耗时: {elapsed:.3f}s | 错误: {str(e)}"
                    )
                else:
                    logger.error(
                        f"[{module_name}] {func_name} 异常 | "
                        f"耗时: {elapsed:.3f}s | 错误: {str(e)}"
                    )
                raise

        return wrapper
    return decorator


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    log_retries: bool = True
):
    """
    重试装饰器

    当函数执行失败时自动重试。

    Args:
        max_attempts: 最大重试次数
        delay: 初始重试延迟（秒）
        backoff: 退避因子
        exceptions: 捕获的异常类型
        log_retries: 是否记录重试日志

    Returns:
        装饰器函数

    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__qualname__} 重试{max_attempts}次后仍失败: {e}"
                        )
                        raise

                    if log_retries:
                        logger.warning(
                            f"{func.__qualname__} 第{attempt}次尝试失败，"
                            f"{current_delay}秒后重试: {e}"
                        )

                    time.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception if last_exception else RuntimeError("未知错误")

        return wrapper
    return decorator


def timing(func: Callable) -> Callable:
    """
    计时装饰器

    记录函数执行时间。

    Example:
        >>> @timing
        ... def process_data():
        ...     time.sleep(1)
        ...     return "done"
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{func.__qualname__} 执行耗时: {elapsed:.3f}秒")
        return result
    return wrapper


def deprecated(reason: str = ""):
    """
    弃用装饰器

    标记函数为已弃用。

    Args:
        reason: 弃用原因

    Example:
        >>> @deprecated("请使用 new_function 代替")
        ... def old_function():
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            message = f"{func.__qualname__} 已弃用"
            if reason:
                message += f": {reason}"
            logger.warning(message)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def singleton(cls):
    """
    单例装饰器

    确保类只有一个实例。

    Example:
        >>> @singleton
        ... class Database:
        ...     pass
    """
    instances = {}

    @functools.wraps(cls)
    def wrapper(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return wrapper


def class_logger(log_level: str = "INFO"):
    """
    类日志装饰器

    为类的所有公共方法自动添加日志记录。
    排除 __init__, __str__ 等特殊方法。

    Args:
        log_level: 日志级别

    Returns:
        装饰器函数

    """
    def decorator(cls):
        # 确保日志已配置
        _ensure_logger_configured()
        
        class_name = cls.__name__
        
        # 遍历类的所有属性
        for attr_name in dir(cls):
            # 跳过私有方法和特殊方法
            if attr_name.startswith("_"):
                continue
            
            attr = getattr(cls, attr_name)
            
            # 只处理方法
            if callable(attr) and not isinstance(attr, property):
                # 为方法添加日志装饰器
                decorated = _create_method_logger(attr, class_name, log_level)
                setattr(cls, attr_name, decorated)
        
        # 包装 __init__ 以记录类实例化
        original_init = cls.__init__
        
        @functools.wraps(original_init)
        def new_init(self, *args, **kwargs):
            logger.log(log_level, f"[{class_name}] 创建实例")
            return original_init(self, *args, **kwargs)
        
        cls.__init__ = new_init
        
        return cls
    
    return decorator


def _create_method_logger(method, class_name: str, log_level: str):
    """为类方法创建日志包装器"""
    method_name = method.__name__
    
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        # 记录方法调用
        args_str = _format_args(args, kwargs)
        logger.log(
            log_level,
            f"[{class_name}.{method_name}] 调用 | 参数: {args_str}"
        )
        
        start_time = time.time()
        
        try:
            result = method(self, *args, **kwargs)
            elapsed = time.time() - start_time
            
            logger.log(
                log_level,
                f"[{class_name}.{method_name}] 完成 | 耗时: {elapsed:.3f}s"
            )
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(
                f"[{class_name}.{method_name}] 异常 | "
                f"耗时: {elapsed:.3f}s | 错误: {str(e)}"
            )
            raise
    
    return wrapper


# ============ 辅助函数 ============

def _setup_function_logger(func: Callable, log_file: str):
    """为函数设置专属日志文件"""
    global _default_log_dir
    
    if _default_log_dir is None:
        _ensure_logger_configured()
    
    log_path = _default_log_dir / log_file
    
    # 检查是否已添加该文件的处理器
    for handler in logger._core.handlers.values():
        if hasattr(handler, '_name') and handler._name == str(log_path):
            return
    
    logger.add(
        str(log_path),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        filter=lambda record: record["extra"].get("func_name") == func.__qualname__
    )


def _format_args(args: tuple, kwargs: dict) -> str:
    """格式化参数"""
    args_str = []

    # 位置参数
    for arg in args:
        args_str.append(_truncate(str(arg), 50))

    # 关键字参数
    for key, value in kwargs.items():
        args_str.append(f"{key}={_truncate(str(value), 50)}")

    return ", ".join(args_str)


def _format_result(result: Any) -> str:
    """格式化返回值"""
    return _truncate(str(result), 100)


def _truncate(text: str, max_length: int) -> str:
    """截断长文本"""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text

def db_retry(
        max_retries: int = 5,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        retriable_errors: Tuple[Type[Exception], ...] = (  # 改为变长元组
                OperationalError,
                TimeoutError,
                DatabaseError,
                ConnectionRefusedError,
                ProtocolError,
                ChunkedEncodingError,
                KeyError,
                Exception
        )
):
    """数据库操作重试装饰器（工业级精简版）"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except retriable_errors as e:
                    last_exception = e
                    if attempt == max_retries:
                        raise  # 最终失败抛出异常

                    # 计算退避时间（指数退避 + 随机抖动）
                    sleep_time = min(delay, max_delay)
                    if jitter:
                        sleep_time *= random.uniform(0.8, 1.2)

                    logger.error(f"操作重试中 | 尝试次数: {attempt}/{max_retries} | "
                          f"等待: {sleep_time:.2f}s | 错误: {str(e)}")

                    delay *= backoff_factor

                except (DataError, ValueError) as e:
                    # 数据类型错误直接抛出（不可重试）
                    raise RuntimeError(f"数据校验失败: {str(e)}") from e

            raise last_exception or RuntimeError("未知数据库错误")
        return wrapper
    return decorator