"""
慢日志服务 - 简化版（避免循环导入）
提供慢日志的查询和统计功能
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List


class SlowLogService:
    """慢日志服务 - 查询和统计"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    def save_slow_frontend_resource_async(self, data: Dict[str, Any]):
        """异步保存前端慢资源记录"""
        try:
            from gs2026.dashboard2.services.slow_log_storage import SlowLogStorage
            SlowLogStorage().save_slow_frontend_resource_async(data)
        except Exception as e:
            print(f"[SlowLogService] 保存前端慢资源失败: {e}")

    def get_stats(self, date: str = None) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            from gs2026.dashboard2.services.slow_log_storage import SlowLogStorage
            return SlowLogStorage().get_stats(date)
        except Exception as e:
            print(f"[SlowLogService] 获取统计信息失败: {e}")
            return {
                'slow_requests': {'total': 0, 'avg_duration': 0, 'max_duration': 0},
                'slow_queries': {'total': 0, 'avg_duration': 0, 'max_duration': 0},
                'slow_frontend': {'total': 0, 'avg_duration': 0, 'max_duration': 0}
            }

    def get_slow_requests(self, date: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取慢请求列表"""
        try:
            from gs2026.dashboard2.services.slow_log_storage import SlowLogStorage
            return SlowLogStorage().get_slow_requests(date, limit)
        except Exception as e:
            print(f"[SlowLogService] 获取慢请求列表失败: {e}")
            return []

    def get_slow_queries(self, date: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取慢查询列表"""
        try:
            from gs2026.dashboard2.services.slow_log_storage import SlowLogStorage
            return SlowLogStorage().get_slow_queries(date, limit)
        except Exception as e:
            print(f"[SlowLogService] 获取慢查询列表失败: {e}")
            return []

    def get_slow_frontend_resources(self, date: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取前端慢资源列表"""
        try:
            from gs2026.dashboard2.services.slow_log_storage import SlowLogStorage
            return SlowLogStorage().get_slow_frontend_resources(date, limit)
        except Exception as e:
            print(f"[SlowLogService] 获取前端慢资源列表失败: {e}")
            return []

    def get_hotspot_analysis(self, days: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """获取热点分析"""
        try:
            from gs2026.dashboard2.services.slow_log_storage import SlowLogStorage
            return SlowLogStorage().get_hotspot_analysis(days)
        except Exception as e:
            print(f"[SlowLogService] 获取热点分析失败: {e}")
            return {'api': [], 'sql': [], 'frontend': []}


def get_slow_log_service() -> SlowLogService:
    """获取慢日志服务实例"""
    return SlowLogService()
