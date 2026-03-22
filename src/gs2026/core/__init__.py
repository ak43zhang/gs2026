"""
核心功能模块

提供应用程序核心功能。
"""

from gs2026.core.application import GS2026App
from gs2026.core.exceptions import (
    GS2026Exception,
    ConfigError,
    CollectionError,
    AnalysisError,
    DatabaseError
)

__all__ = [
    "GS2026App",
    "GS2026Exception",
    "ConfigError",
    "CollectionError",
    "AnalysisError",
    "DatabaseError"
]
