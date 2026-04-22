"""验证器基类"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any
import pandas as pd
from sqlalchemy import create_engine, text

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import ValidationRule, InvalidRecord, ValidationReport
from rules.engine import RuleEngine


class BaseValidator(ABC):
    """验证器基类"""
    
    def __init__(self, config: Dict[str, Any], mysql_engine):
        self.config = config
        self.engine = mysql_engine
        self.rule_engine = RuleEngine(self._build_rules())
    
    @abstractmethod
    def get_table_name(self, year: str) -> str:
        """获取表名"""
        pass
    
    @abstractmethod
    def get_source_table(self, content_hash: str) -> str:
        """获取源表名"""
        pass
    
    @property
    @abstractmethod
    def validator_type(self) -> str:
        """验证器类型标识"""
        pass
    
    def _build_rules(self) -> List[ValidationRule]:
        """构建规则列表"""
        rules = []
        for rule_config in self.config.get('rules', []):
            params = {k: v for k, v in rule_config.items() 
                     if k not in ['name', 'field', 'type', 'description']}
            rules.append(ValidationRule(
                name=rule_config['name'],
                field=rule_config['field'],
                type=rule_config['type'],
                params=params,
                description=rule_config.get('description', '')
            ))
        return rules
    
    def validate(self, start_date: str, end_date: str) -> ValidationReport:
        """执行验证"""
        from datetime import datetime
        
        start_time = datetime.now()
        
        # 查询数据
        records = self._fetch_records(start_date, end_date)
        
        # 逐条验证
        invalid_records = []
        for record in records:
            errors = self.rule_engine.validate(record)
            if errors:
                invalid_records.append(InvalidRecord(
                    content_hash=record.get('content_hash', ''),
                    table_name=self.get_table_name(start_date[:4]),
                    source_table=self.get_source_table(record.get('content_hash', '')),
                    errors=errors,
                    raw_data=record
                ))
        
        end_time = datetime.now()
        
        return ValidationReport(
            validator_type=self.validator_type,
            start_date=start_date,
            end_date=end_date,
            total_records=len(records),
            invalid_records=invalid_records,
            start_time=start_time,
            end_time=end_time
        )
    
    def _fetch_records(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """从数据库获取记录"""
        year = start_date[:4]
        table_name = self.get_table_name(year)
        date_field = self.config.get('date_field', 'publish_time')
        
        # 转换日期格式
        start_datetime = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]} 00:00:00"
        end_datetime = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]} 23:59:59"
        
        sql = f"""
            SELECT * FROM {table_name}
            WHERE {date_field} BETWEEN '{start_datetime}' AND '{end_datetime}'
        """
        
        try:
            df = pd.read_sql(sql, self.engine)
            return df.to_dict('records')
        except Exception as e:
            print(f"查询数据失败: {e}")
            return []
