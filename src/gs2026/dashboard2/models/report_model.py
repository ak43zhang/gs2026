"""
报表中心数据模型
数据库: gs_platform
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, Boolean, BigInteger, JSON, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class ReportType(Base):
    """报告类型配置"""
    __tablename__ = 'report_types'
    
    report_type_id = Column(Integer, primary_key=True, autoincrement=True)
    report_type_code = Column(String(50), unique=True, nullable=False)
    report_type_name = Column(String(100), nullable=False)
    report_type_icon = Column(String(50), default='📄')
    report_type_description = Column(Text)
    report_type_output_dir = Column(String(200), nullable=False)
    report_type_default_format = Column(String(20), default='pdf')
    report_type_supported_formats = Column(JSON)
    report_type_is_active = Column(Boolean, default=True)
    report_type_sort_order = Column(Integer, default=0)
    report_type_created_at = Column(DateTime, default=datetime.now)
    report_type_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联关系
    reports = relationship("Report", back_populates="report_type_ref")
    
    def to_dict(self):
        return {
            'report_type_id': self.report_type_id,
            'report_type_code': self.report_type_code,
            'report_type_name': self.report_type_name,
            'report_type_icon': self.report_type_icon,
            'report_type_description': self.report_type_description,
            'report_type_output_dir': self.report_type_output_dir,
            'report_type_default_format': self.report_type_default_format,
            'report_type_supported_formats': self.report_type_supported_formats,
            'report_type_is_active': self.report_type_is_active,
            'report_type_sort_order': self.report_type_sort_order,
            'report_type_created_at': self.report_type_created_at.isoformat() if self.report_type_created_at else None,
            'report_type_updated_at': self.report_type_updated_at.isoformat() if self.report_type_updated_at else None
        }


class Report(Base):
    """报告元数据"""
    __tablename__ = 'reports'
    __table_args__ = (
        Index('idx_report_type_date', 'report_type', 'report_date'),
        Index('idx_report_format', 'report_file_format'),
        Index('idx_report_date', 'report_date'),
    )
    
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(50), ForeignKey('report_types.report_type_code'), nullable=False)
    report_name = Column(String(255), nullable=False)
    report_date = Column(Date, nullable=False)
    report_file_path = Column(String(500), nullable=False)
    report_file_format = Column(String(20), nullable=False)
    report_file_size = Column(BigInteger, default=0)
    report_page_count = Column(Integer, default=0)
    report_content_text = Column(Text)
    report_tts_status = Column(String(20), default='pending')
    report_tts_duration = Column(Integer, default=0)
    report_tts_audio_path = Column(String(500))
    report_params = Column(JSON)
    report_status = Column(String(20), default='completed')
    report_created_at = Column(DateTime, default=datetime.now)
    report_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联关系
    report_type_ref = relationship("ReportType", back_populates="reports")
    generation_task = relationship("ReportTask", back_populates="report_result", uselist=False)
    
    def to_dict(self, include_content=False):
        data = {
            'report_id': self.report_id,
            'report_type': self.report_type,
            'report_name': self.report_name,
            'report_date': self.report_date.isoformat() if self.report_date else None,
            'report_file_path': self.report_file_path,
            'report_file_format': self.report_file_format,
            'report_file_size': self.report_file_size,
            'report_page_count': self.report_page_count,
            'report_tts_status': self.report_tts_status,
            'report_tts_duration': self.report_tts_duration,
            'report_tts_audio_path': self.report_tts_audio_path,
            'report_status': self.report_status,
            'report_created_at': self.report_created_at.isoformat() if self.report_created_at else None,
            'report_updated_at': self.report_updated_at.isoformat() if self.report_updated_at else None
        }
        if include_content:
            data['report_content_text'] = self.report_content_text
        return data


class ReportTask(Base):
    """报告生成任务"""
    __tablename__ = 'report_tasks'
    
    report_task_id = Column(String(50), primary_key=True)
    report_type = Column(String(50), ForeignKey('report_types.report_type_code'), nullable=False)
    report_date = Column(Date, nullable=False)
    report_format = Column(String(20))
    report_task_status = Column(String(20), default='pending')
    report_task_progress = Column(Integer, default=0)
    report_task_message = Column(Text)
    report_task_params = Column(JSON)
    report_task_result_id = Column(Integer, ForeignKey('reports.report_id'))
    report_task_error = Column(Text)
    report_task_started_at = Column(DateTime)
    report_task_completed_at = Column(DateTime)
    report_task_created_at = Column(DateTime, default=datetime.now)
    report_task_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联关系
    report_result = relationship("Report", back_populates="generation_task")
    
    def to_dict(self):
        return {
            'report_task_id': self.report_task_id,
            'report_type': self.report_type,
            'report_date': self.report_date.isoformat() if self.report_date else None,
            'report_format': self.report_format,
            'report_task_status': self.report_task_status,
            'report_task_progress': self.report_task_progress,
            'report_task_message': self.report_task_message,
            'report_task_params': self.report_task_params,
            'report_task_result_id': self.report_task_result_id,
            'report_task_error': self.report_task_error,
            'report_task_started_at': self.report_task_started_at.isoformat() if self.report_task_started_at else None,
            'report_task_completed_at': self.report_task_completed_at.isoformat() if self.report_task_completed_at else None,
            'report_task_created_at': self.report_task_created_at.isoformat() if self.report_task_created_at else None,
            'report_task_updated_at': self.report_task_updated_at.isoformat() if self.report_task_updated_at else None
        }
