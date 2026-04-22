"""数据模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any


@dataclass
class ValidationRule:
    """验证规则"""
    name: str
    field: str
    type: str  # range, enum, formula, not_null, regex
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class InvalidRecord:
    """异常记录"""
    content_hash: str
    table_name: str
    source_table: str
    errors: List[str]
    raw_data: Dict[str, Any]


@dataclass
class ValidationReport:
    """验证报告"""
    validator_type: str
    start_date: str
    end_date: str
    total_records: int
    invalid_records: List[InvalidRecord]
    start_time: datetime
    end_time: Optional[datetime] = None
    
    @property
    def invalid_count(self) -> int:
        return len(self.invalid_records)
    
    @property
    def invalid_rate(self) -> float:
        if self.total_records == 0:
            return 0.0
        return self.invalid_count / self.total_records * 100
    
    @property
    def duration_seconds(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()


@dataclass
class FixReport:
    """修复报告"""
    validation_report: ValidationReport
    deleted_mysql: int = 0
    deleted_redis: int = 0
    marked_source: int = 0
    errors: List[str] = field(default_factory=list)
