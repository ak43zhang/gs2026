"""新闻分析验证器"""
from typing import Dict, Any
from .base import BaseValidator


class NewsValidator(BaseValidator):
    """新闻分析验证器"""
    
    @property
    def validator_type(self) -> str:
        return "news"
    
    def get_table_name(self, year: str) -> str:
        return f"analysis_news_detail_{year}"
    
    def get_source_table(self, content_hash: str) -> str:
        """根据content_hash查询源表"""
        # 简化实现：返回可能的源表列表
        # 实际应根据content_hash前缀或数据库查询确定
        return "news_cls2026/news_combine2026"
