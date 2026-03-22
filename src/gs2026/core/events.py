"""
事件系统模块

提供应用程序事件发布和订阅功能。
"""

import logging
from typing import Callable, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Event:
    """事件数据类"""
    name: str
    data: Any
    timestamp: datetime
    source: str


class EventBus:
    """
    事件总线
    
    提供事件的发布和订阅功能。
    
    Example:
        >>> bus = EventBus()
        >>> bus.subscribe("stock.update", handler)
        >>> bus.publish("stock.update", data)
    """
    
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self.logger = logging.getLogger("gs2026.events")
    
    def subscribe(self, event_name: str, handler: Callable) -> None:
        """
        订阅事件
        
        Args:
            event_name: 事件名称
            handler: 处理函数
        """
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)
        self.logger.debug(f"订阅事件: {event_name}")
    
    def unsubscribe(self, event_name: str, handler: Callable) -> None:
        """
        取消订阅
        
        Args:
            event_name: 事件名称
            handler: 处理函数
        """
        if event_name in self._handlers:
            self._handlers[event_name].remove(handler)
    
    def publish(self, event_name: str, data: Any, source: str = "") -> None:
        """
        发布事件
        
        Args:
            event_name: 事件名称
            data: 事件数据
            source: 事件来源
        """
        event = Event(
            name=event_name,
            data=data,
            timestamp=datetime.now(),
            source=source
        )
        
        handlers = self._handlers.get(event_name, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(f"事件处理异常: {e}")


# 全局事件总线
event_bus = EventBus()
