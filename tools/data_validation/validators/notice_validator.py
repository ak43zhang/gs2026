"""公告分析验证器"""
from typing import Dict, Any
from .base import BaseValidator


class NoticeValidator(BaseValidator):
    """公告分析验证器"""
    
    @property
    def validator_type(self) -> str:
        return "notice"
    
    def get_table_name(self, year: str) -> str:
        return f"analysis_notice_detail_{year}"
    
    def get_source_table(self, content_hash: str) -> str:
        return "notice2026"
