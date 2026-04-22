"""验证器模块初始化"""
from .news_validator import NewsValidator
from .ztb_validator import ZtbValidator
from .notice_validator import NoticeValidator
from .domain_validator import DomainValidator

__all__ = ['NewsValidator', 'ZtbValidator', 'NoticeValidator', 'DomainValidator']
