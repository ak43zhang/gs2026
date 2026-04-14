"""
WebSocket 通知模块 - 股债联动实时推送

独立模块，不侵入原有代码
通过导入方式集成到 monitor_gp_zq_rising_signal.py
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional

from flask import Flask
from flask_socketio import SocketIO, emit
from loguru import logger

# 全局 SocketIO 实例（延迟初始化）
_socketio: Optional[SocketIO] = None


def init_socketio(app: Flask) -> SocketIO:
    """
    初始化 SocketIO
    
    Args:
        app: Flask 应用实例
    
    Returns:
        SocketIO 实例
    """
    global _socketio
    
    if _socketio is None:
        _socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            async_mode='threading',
            logger=False,
            engineio_logger=False
        )
        logger.info("SocketIO 初始化完成")
    
    return _socketio


def get_socketio() -> Optional[SocketIO]:
    """获取 SocketIO 实例"""
    return _socketio


def notify_new_signal(data: Dict[str, Any]):
    """
    发送新信号通知
    
    Args:
        data: 信号数据，包含股票、债券信息
    """
    if _socketio is None:
        return
    
    try:
        # 构建通知消息
        message = {
            'type': 'new_signal',
            'timestamp': datetime.now().isoformat(),
            'data': {
                'stock_code': data.get('code_gp', ''),
                'stock_name': data.get('name_gp', ''),
                'bond_code': data.get('code', ''),
                'bond_name': data.get('name', ''),
                'time': data.get('time', ''),
                'zf_30_gp': data.get('zf_30_gp', 0),
                'zf_30_zq': data.get('zf_30_zq', 0),
            }
        }
        
        # 广播到所有连接的客户端
        _socketio.emit('new_signal', message, broadcast=True, namespace='/')
        logger.info(f"WebSocket 通知已发送: {message['data']['stock_code']}")
        
    except Exception as e:
        logger.error(f"WebSocket 通知失败: {e}")


def notify_connection_status(connected: bool, sid: str = None):
    """通知连接状态变化"""
    if _socketio is None:
        return
    
    try:
        message = {
            'type': 'connection_status',
            'connected': connected,
            'sid': sid,
            'timestamp': datetime.now().isoformat()
        }
        _socketio.emit('connection_status', message, broadcast=True, namespace='/')
    except Exception as e:
        logger.error(f"连接状态通知失败: {e}")
