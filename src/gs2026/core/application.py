"""
应用程序核心模块

提供GS2026应用程序的主入口和生命周期管理。
"""

import logging
import signal
import sys
from pathlib import Path
from typing import Optional, List, Callable

from gs2026.config.settings import settings
from gs2026.utils.logger import setup_logger


class GS2026App:
    """
    GS2026应用程序主类
    
    管理应用程序的生命周期，包括初始化、启动和关闭。
    
    Attributes:
        name: 应用名称
        version: 版本号
        logger: 日志记录器
        _initialized: 是否已初始化
        _running: 是否运行中
        _shutdown_handlers: 关闭处理器列表
        
    """

    
    def __init__(self, name: str = "GS2026"):
        """
        初始化应用程序
        
        Args:
            name: 应用名称
        """
        self.name = name
        self.version = "2026.1.0"
        self.logger: Optional[logging.Logger] = None
        self._initialized = False
        self._running = False
        self._shutdown_handlers: List[Callable] = []
        
        # 注册信号处理
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame) -> None:
        """信号处理器"""
        if self.logger:
            self.logger.info(f"接收到信号 {signum}，正在关闭...")
        self.shutdown()
        sys.exit(0)
    
    def initialize(self) -> None:
        """
        初始化应用程序
        
        设置日志、数据库连接等。
        """
        if self._initialized:
            return
        
        # 设置日志
        self.logger = setup_logger(
            name=self.name,
            log_dir=settings.log_dir
        )
        self.logger.info(f"Initializing {self.name} v{self.version}")
        
        self._initialized = True
        self.logger.info("Application initialized successfully")
    
    def run(self) -> None:
        """
        运行应用程序
        
        主运行循环。
        """
        if not self._initialized:
            self.initialize()
        
        self._running = True
        self.logger.info(f"{self.name} is running")
        
        try:
            # 主循环
            while self._running:
                # 这里可以添加主业务逻辑
                import time
                time.sleep(1)
        except Exception as e:
            self.logger.error(f"运行异常: {e}")
            raise
    
    def shutdown(self) -> None:
        """
        关闭应用程序
        
        清理资源，关闭连接。
        """
        if not self._initialized:
            return
        
        self._running = False
        
        # 执行关闭处理器
        for handler in self._shutdown_handlers:
            try:
                handler()
            except Exception as e:
                if self.logger:
                    self.logger.error(f"关闭处理器异常: {e}")
        
        if self.logger:
            self.logger.info(f"{self.name} shutdown complete")
        
        self._initialized = False
    
    def register_shutdown_handler(self, handler: Callable) -> None:
        """
        注册关闭处理器
        
        Args:
            handler: 关闭时执行的函数
        """
        self._shutdown_handlers.append(handler)
    
    @property
    def is_running(self) -> bool:
        """是否运行中"""
        return self._running
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
