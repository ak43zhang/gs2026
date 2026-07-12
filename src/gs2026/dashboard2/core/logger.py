"""
日志管理器 - 统一日志配置
- 分级日志（DEBUG/INFO/WARNING/ERROR）
- 按模块分类
- 自动轮转（按日期）
- 控制台+文件双输出
"""

import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

class LoggerManager:
    """日志管理器"""
    
    @staticmethod
    def setup(app_name='dashboard2', log_dir='logs', level=logging.INFO):
        """
        配置应用日志
        
        Args:
            app_name: 应用名称
            log_dir: 日志目录
            level: 日志级别
        
        Returns:
            logger实例
        """
        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
        
        # 创建logger
        logger = logging.getLogger(app_name)
        logger.setLevel(level)
        
        # 避免重复添加handler
        if logger.handlers:
            return logger
        
        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台handler（只输出WARNING及以上）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 文件handler（按日期轮转）
        file_handler = TimedRotatingFileHandler(
            log_path / f'{app_name}.log',
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 错误日志单独文件
        from logging.handlers import RotatingFileHandler
        error_handler = RotatingFileHandler(
            log_path / f'{app_name}_error.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)
        
        # 抑制werkzeug请求日志（INFO级别的200/304等正常请求不打印，仅保留WARNING+）
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        
        return logger
