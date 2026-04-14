"""
报告生成基类
"""
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Dict, Any


class ReportGenerator(ABC):
    """报告生成器基类"""
    
    # 子类必须定义
    report_type: str = None
    report_name: str = None
    
    @abstractmethod
    def generate(self, report_date: date, output_format: str = 'pdf',
                 params: Dict = None) -> Dict[str, Any]:
        """
        生成报告
        
        Args:
            report_date: 报告日期
            output_format: 输出格式 (pdf, epub, md, etc.)
            params: 额外参数
        
        Returns:
            dict: {
                'file_path': '相对路径',
                'file_size': 1024,
                'page_count': 10,
                'content_text': '纯文本内容',
                'data': {...}
            }
        """
        pass
    
    @abstractmethod
    def get_report_name(self, report_date: date) -> str:
        """获取报告名称"""
        pass


class ReportGeneratorFactory:
    """报告生成器工厂"""
    
    _generators = {}
    
    @classmethod
    def register(cls, generator_class):
        """注册生成器"""
        instance = generator_class()
        cls._generators[instance.report_type] = generator_class
        return generator_class
    
    @classmethod
    def get_generator(cls, report_type: str) -> ReportGenerator:
        """获取生成器"""
        generator_class = cls._generators.get(report_type)
        if not generator_class:
            raise ValueError(f'不支持的报告类型: {report_type}')
        return generator_class()
    
    @classmethod
    def get_supported_types(cls) -> list:
        """获取支持的类型列表"""
        return list(cls._generators.keys())
