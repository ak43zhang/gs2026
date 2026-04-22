"""领域分析验证器"""
from typing import Dict, Any
from .base import BaseValidator


class DomainValidator(BaseValidator):
    """领域分析验证器"""
    
    @property
    def validator_type(self) -> str:
        return "domain"
    
    def get_table_name(self, year: str) -> str:
        return f"analysis_domain_detail_{year}"
    
    def get_source_table(self, content_hash: str) -> str:
        return "domain_events2026"
