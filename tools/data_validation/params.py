"""参数类"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ValidationParams:
    """验证参数"""
    start_date: str = None                    # 开始日期 (YYYYMMDD)
    end_date: str = None                      # 结束日期 (YYYYMMDD)
    validator_types: List[str] = None         # 验证类型列表，None表示全部
    mode: str = 'check'                       # 执行模式: check/fix/report/interactive
    output_dir: str = './reports'             # 报告输出目录
    config_path: str = None                   # 验证规则配置文件路径
    auto_fix: bool = False                    # 是否自动修复
    interactive: bool = False                 # 是否交互模式
    
    def to_dict(self) -> dict:
        return {
            'start_date': self.start_date,
            'end_date': self.end_date,
            'validator_types': self.validator_types,
            'mode': self.mode,
            'output_dir': self.output_dir,
            'config_path': self.config_path,
            'auto_fix': self.auto_fix,
            'interactive': self.interactive
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ValidationParams':
        # 过滤掉None值，使用默认值
        filtered = {k: v for k, v in data.items() if v is not None}
        return cls(**filtered)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ValidationParams':
        import json
        return cls.from_dict(json.loads(json_str))


@dataclass
class ValidationResult:
    """验证结果"""
    success: bool = True
    reports: List[Any] = field(default_factory=list)
    fix_report: Any = None
    output_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'reports': [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.reports],
            'fix_report': self.fix_report.to_dict() if self.fix_report and hasattr(self.fix_report, 'to_dict') else self.fix_report,
            'output_files': self.output_files,
            'errors': self.errors
        }
