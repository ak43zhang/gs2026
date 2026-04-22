"""离线数据验证工具

导出函数:
    - run_validation: 执行数据验证
    - batch_validate: 批量验证
    - run_yaml_tasks: 执行YAML任务
    - time_task_do_validation: 定时任务入口
    - ValidationParams: 参数类
    - ValidationResult: 结果类

使用示例:
    from tools.data_validation import run_validation, ValidationParams
    
    # 方式1: 直接传参
    result = run_validation(
        start_date='20260422',
        end_date='20260422',
        validator_types=['news'],
        mode='check'
    )
    
    # 方式2: 使用参数对象
    params = ValidationParams(
        start_date='20260422',
        end_date='20260422',
        validator_types=['news']
    )
    result = run_validation(params=params)
    
    # 方式3: YAML任务
    result = run_validation(
        yaml_config='config/validation_tasks.yaml',
        task_name='daily_news_validation'
    )
    
    # 方式4: 批量YAML任务
    results = run_yaml_tasks(batch_group='daily_all')
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from .data_validator import run_validation, batch_validate, run_yaml_tasks, time_task_do_validation
from .params import ValidationParams, ValidationResult
from .yaml_loader import YamlConfigLoader

__all__ = [
    'run_validation',
    'batch_validate',
    'run_yaml_tasks',
    'time_task_do_validation',
    'ValidationParams',
    'ValidationResult',
    'YamlConfigLoader'
]
