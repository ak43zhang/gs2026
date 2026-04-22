"""涨停分析验证器"""
from typing import Dict, Any
from .base import BaseValidator


class ZtbValidator(BaseValidator):
    """涨停分析验证器"""
    
    @property
    def validator_type(self) -> str:
        return "ztb"
    
    def get_table_name(self, year: str) -> str:
        return f"analysis_ztb_detail_{year}"
    
    def get_source_table(self, content_hash: str) -> str:
        """涨停分析没有源表概念，返回空"""
        return ""
