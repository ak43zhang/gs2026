"""
报告导出器基类
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any


class ReportExporter(ABC):
    """报告导出器基类"""
    
    @property
    @abstractmethod
    def format(self) -> str:
        """导出格式"""
        pass
    
    @abstractmethod
    def export(self, data: Dict[str, Any], output_path: Path) -> Path:
        """
        导出报告
        
        Args:
            data: 报告数据
            output_path: 输出文件路径
        
        Returns:
            Path: 导出的文件路径
        """
        pass
    
    def extract_text(self, file_path: Path) -> str:
        """
        从导出文件中提取纯文本（用于语音播报）
        
        Args:
            file_path: 文件路径
        
        Returns:
            str: 纯文本内容
        """
        # 默认实现，子类可覆盖
        return ''
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """
        获取文件信息
        
        Args:
            file_path: 文件路径
        
        Returns:
            dict: {file_size, page_count}
        """
        stat = file_path.stat()
        return {
            'file_size': stat.st_size,
            'page_count': 0  # 子类可覆盖
        }


class ExporterFactory:
    """导出器工厂"""
    
    _exporters = {}
    
    @classmethod
    def register(cls, exporter_class):
        """注册导出器"""
        instance = exporter_class()
        cls._exporters[instance.format] = exporter_class
        return exporter_class
    
    @classmethod
    def get_exporter(cls, format: str) -> ReportExporter:
        """获取导出器"""
        exporter_class = cls._exporters.get(format)
        if not exporter_class:
            raise ValueError(f'不支持的导出格式: {format}')
        return exporter_class()
    
    @classmethod
    def get_supported_formats(cls) -> list:
        """获取支持的格式列表"""
        return list(cls._exporters.keys())
