"""
日志工具类
"""
import os
import sys
from pathlib import Path
from typing import Final

from loguru import logger


def setup_logger(current_file_name: str) -> logger:
    """
    设置日志配置，自动获取当前执行文件名作为日志名称
    日志将保存在项目根目录的logs文件夹下

    Args:
        current_file_name: 当前文件名

    Returns:
        配置好的logger实例
    """
    # 1. 定义日志目录路径
    root_path = get_project_root()

    log_dir = Path(rf"{root_path}\logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # 3. 构建完整的日志文件路径
    cfn = (current_file_name.replace(root_path, '')
           .replace('\\', '-')
           .replace('.py', '.log')
           .strip('_')[1:])
    log_file_path = log_dir / f"{cfn}"

    # 4. 移除默认的 stderr 处理器
    logger.remove()

    # 5. 添加文件处理器
    logger.add(
        log_file_path,
        format="{time:YYYY-MM-DD HH:mm:ss} |"
               " {level} |"
               " {name}:{function}:{line} |"
               " {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
    )

    # 6. 同时添加控制台输出
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level}</level> | "
               "<cyan>{name}:{function}:{line}</cyan> | "
               "<level>{message}</level>",
        level="INFO"
    )

    return logger


# 获取当前文件的绝对路径
current_file = Path(__file__).resolve()


def get_project_root(marker_files: list = None) -> str:
    """
    根据项目标志文件查找项目根目录

    Args:
        marker_files: 项目标志文件列表，默认为 ['.git', 'setup.py', 'pyproject.toml', 'requirements.txt']

    Returns:
        项目根目录路径
    """
    if marker_files is None:
        marker_files = ['.git', 'setup.py', 'pyproject.toml', 'requirements.txt']

    current_path = current_file
    for parent in current_path.parents:
        if any((parent / marker).exists() for marker in marker_files):
            return str(parent)
    return str(current_path.parent)


# 使用示例
if __name__ == "__main__":
    ABS_PATH_PATHLIB: Final[str] = str(Path(__file__).absolute())
    # 初始化日志配置
    log = setup_logger(ABS_PATH_PATHLIB)

    # 显示日志文件位置
    logger.info(f"日志文件保存在: {Path(os.getcwd()) / 'logs'}")
