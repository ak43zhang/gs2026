"""验证规则引擎"""
import re
from typing import Dict, List, Optional, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import ValidationRule


class RuleEngine:
    """规则引擎"""
    
    def __init__(self, rules: List[ValidationRule]):
        self.rules = rules
    
    def validate(self, record: Dict[str, Any]) -> List[str]:
        """验证单条记录，返回错误列表"""
        errors = []
        for rule in self.rules:
            error = self._check_rule(rule, record)
            if error:
                errors.append(error)
        return errors
    
    def _check_rule(self, rule: ValidationRule, record: Dict[str, Any]) -> Optional[str]:
        """检查单条规则"""
        value = record.get(rule.field)
        
        if rule.type == 'range':
            return self._check_range(rule, value)
        elif rule.type == 'enum':
            return self._check_enum(rule, value)
        elif rule.type == 'formula':
            return self._check_formula(rule, value, record)
        elif rule.type == 'not_null':
            return self._check_not_null(rule, value)
        elif rule.type == 'regex':
            return self._check_regex(rule, value)
        
        return None
    
    def _check_range(self, rule: ValidationRule, value: Any) -> Optional[str]:
        """区间验证"""
        if value is None:
            return f"{rule.name}: 字段值为空"
        
        try:
            num_value = float(value)
        except (TypeError, ValueError):
            return f"{rule.name}: 值 '{value}' 不是有效数字"
        
        min_val = rule.params.get('min')
        max_val = rule.params.get('max')
        
        if min_val is not None and num_value < min_val:
            return f"{rule.name}: {num_value} 小于最小值 {min_val}"
        if max_val is not None and num_value > max_val:
            return f"{rule.name}: {num_value} 大于最大值 {max_val}"
        
        return None
    
    def _check_enum(self, rule: ValidationRule, value: Any) -> Optional[str]:
        """枚举验证"""
        allowed = rule.params.get('values', [])
        if value not in allowed:
            return f"{rule.name}: '{value}' 不在允许值 {allowed} 中"
        return None
    
    def _check_formula(self, rule: ValidationRule, value: Any, record: Dict[str, Any]) -> Optional[str]:
        """公式验证"""
        if value is None:
            return f"{rule.name}: 字段值为空"
        
        formula = rule.params.get('formula', '')
        tolerance = rule.params.get('tolerance', 0)
        
        try:
            expected = self._eval_formula(formula, record)
            actual = float(value)
            if abs(actual - expected) > tolerance:
                return f"{rule.name}: 实际值 {actual} 与公式计算值 {expected} 不一致 (公式: {formula})"
        except Exception as e:
            return f"{rule.name}: 公式计算失败 - {str(e)}"
        
        return None
    
    def _check_not_null(self, rule: ValidationRule, value: Any) -> Optional[str]:
        """非空验证"""
        if value is None or value == '':
            return f"{rule.name}: 字段不能为空"
        return None
    
    def _check_regex(self, rule: ValidationRule, value: Any) -> Optional[str]:
        """正则验证"""
        if value is None:
            return f"{rule.name}: 字段值为空"
        
        pattern = rule.params.get('pattern', '')
        if not re.match(pattern, str(value)):
            return f"{rule.name}: '{value}' 不符合格式要求 (模式: {pattern})"
        return None
    
    def _eval_formula(self, formula: str, record: Dict[str, Any]) -> float:
        """安全计算公式值"""
        # 创建安全的计算环境
        safe_dict = {'__builtins__': {}}
        
        # 将记录中的字段添加到计算环境
        for key, val in record.items():
            if isinstance(val, (int, float)):
                safe_dict[key] = val
            elif isinstance(val, str):
                try:
                    safe_dict[key] = float(val)
                except ValueError:
                    safe_dict[key] = 0
        
        try:
            result = eval(formula, safe_dict)
            return float(result)
        except Exception as e:
            raise ValueError(f"公式 '{formula}' 计算失败: {str(e)}")
