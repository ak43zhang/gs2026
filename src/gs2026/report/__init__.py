"""
报告生成模块
"""
from .base import ReportGenerator, ReportGeneratorFactory
from .zt_report.generator import ZTReportGenerator

# 注册生成器
ReportGeneratorFactory.register(ZTReportGenerator)

__all__ = [
    'ReportGenerator',
    'ReportGeneratorFactory',
    'ZTReportGenerator',
]
