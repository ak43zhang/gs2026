"""
自定义异常模块

定义项目中使用的所有自定义异常。
"""


class GS2026Exception(Exception):
    """基础异常类"""
    
    def __init__(self, message: str = "", code: str = ""):
        self.message = message
        self.code = code
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class ConfigError(GS2026Exception):
    """配置错误"""
    pass


class CollectionError(GS2026Exception):
    """采集错误"""
    pass


class AnalysisError(GS2026Exception):
    """分析错误"""
    pass


class DatabaseError(GS2026Exception):
    """数据库错误"""
    pass


class ValidationError(GS2026Exception):
    """数据验证错误"""
    pass


class NotificationError(GS2026Exception):
    """通知错误"""
    pass
