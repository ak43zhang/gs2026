# 离线数据验证工具设计方案 v3（YAML配置版）

> 创建时间: 2026-04-22 18:11
> 版本: 3.0
> 特性: YAML配置文件 + 函数传参

---

## 一、设计思路

参考 `deepseek_analysis_news_ztb.py` 的实现方式：

1. **YAML配置文件**: 集中管理验证任务参数，便于批量配置和版本控制
2. **函数传参**: 支持代码中直接调用，便于集成到其他模块
3. **灵活组合**: 支持单条验证、批量验证、定时任务等多种模式

---

## 二、YAML配置文件设计

### 2.1 配置文件位置

```
gs2026/
├── config/
│   └── validation_tasks.yaml      # 验证任务配置文件
└── tools/data_validation/
    └── ...
```

### 2.2 配置文件结构

```yaml
# config/validation_tasks.yaml

# 全局配置
global:
  # MySQL连接配置（可选，默认使用项目配置）
  mysql:
    host: "192.168.0.101"
    port: 3306
    user: "root"
    password: "${MYSQL_PASSWORD}"  # 支持环境变量
    database: "gs"
  
  # Redis连接配置（可选）
  redis:
    host: "localhost"
    port: 6379
    db: 0
  
  # 报告输出目录
  output_dir: "./reports/validation"
  
  # 验证规则配置文件路径
  validation_config: "tools/data_validation/config/validation_config.json"

# 验证任务定义
tasks:
  # 任务1: 每日新闻分析数据验证
  - name: "daily_news_validation"
    description: "每日新闻分析数据质量验证"
    enabled: true
    schedule: "0 2 * * *"  # 定时任务表达式（可选）
    
    # 验证参数
    params:
      start_date: "${YESTERDAY}"  # 支持变量: TODAY, YESTERDAY, TOMORROW
      end_date: "${YESTERDAY}"
      validator_types:
        - "news"
      mode: "check"
      auto_fix: false
      interactive: false
    
    # 通知配置（可选）
    notification:
      on_error: true
      on_warning: true
      channels:
        - type: "email"
          recipients: ["admin@example.com"]
        - type: "webhook"
          url: "https://hooks.example.com/validation"

  # 任务2: 每周全量数据验证
  - name: "weekly_full_validation"
    description: "每周全量数据质量验证"
    enabled: true
    
    params:
      start_date: "${WEEK_AGO}"
      end_date: "${TODAY}"
      validator_types:
        - "news"
        - "ztb"
        - "notice"
        - "domain"
      mode: "fix"  # 自动修复
      auto_fix: true
      interactive: false

  # 任务3: 历史数据批量修复
  - name: "history_data_fix"
    description: "修复2026-04-01到2026-04-22的历史数据"
    enabled: false  # 默认禁用，手动触发
    
    params:
      start_date: "20260401"
      end_date: "20260422"
      validator_types:
        - "news"
      mode: "fix"
      auto_fix: true

  # 任务4: 涨停分析专项验证
  - name: "ztb_special_check"
    description: "涨停分析数据专项验证"
    enabled: true
    
    params:
      start_date: "${TODAY}"
      end_date: "${TODAY}"
      validator_types:
        - "ztb"
      mode: "check"

# 批量任务组（用于一次性执行多个相关任务）
batch_groups:
  - name: "daily_all"
    description: "每日所有数据验证"
    tasks:
      - "daily_news_validation"
      - "ztb_special_check"
  
  - name: "weekly_maintenance"
    description: "每周数据维护"
    tasks:
      - "weekly_full_validation"
```

### 2.3 支持的变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `${TODAY}` | 今天 | 20260422 |
| `${YESTERDAY}` | 昨天 | 20260421 |
| `${TOMORROW}` | 明天 | 20260423 |
| `${WEEK_AGO}` | 7天前 | 20260415 |
| `${MONTH_AGO}` | 30天前 | 20260323 |
| `${MYSQL_PASSWORD}` | 环境变量 | 从环境变量读取 |

---

## 三、函数接口设计

### 3.1 主入口函数

```python
def run_validation(
    start_date: str = None,
    end_date: str = None,
    validator_types: List[str] = None,
    mode: str = 'check',
    output_dir: str = './reports',
    config_path: str = None,
    auto_fix: bool = False,
    interactive: bool = False,
    mysql_engine = None,
    redis_client = None,
    params: ValidationParams = None,
    yaml_config: str = None,        # 新增: YAML配置文件路径
    task_name: str = None           # 新增: YAML中定义的任务名
) -> Dict[str, Any]:
    """
    执行数据验证
    
    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        validator_types: 验证类型列表 ['ztb', 'news', 'notice', 'domain']，None表示全部
        mode: 执行模式 'check'/'fix'/'report'
        output_dir: 报告输出目录
        config_path: 验证规则配置文件路径
        auto_fix: 是否自动清理（mode='fix'时生效）
        interactive: 是否交互模式
        mysql_engine: MySQL引擎（None时自动创建）
        redis_client: Redis客户端（None时自动创建）
        params: ValidationParams对象（直接传参方式）
        yaml_config: YAML配置文件路径
        task_name: YAML中定义的任务名称
    
    Returns:
        {
            'success': bool,
            'reports': List[ValidationReport],
            'fix_report': FixReport (mode='fix'时),
            'output_files': List[str] (mode='report'时),
            'errors': List[str]
        }
    """
```

### 3.2 批量验证函数

```python
def batch_validate(
    date_list: List[str],
    validator_types: List[str] = None,
    mode: str = 'check',
    **kwargs
) -> Dict[str, Any]:
    """
    批量验证多个日期
    
    Args:
        date_list: 日期列表 ['20260422', '20260423', ...]
        validator_types: 验证类型列表
        mode: 执行模式
        **kwargs: 其他参数传递给run_validation
    
    Returns:
        汇总后的验证结果
    """
```

### 3.3 定时任务入口

```python
def time_task_do_validation(
    date_param: str,
    start_date: str,
    end_date: str,
    validator_types: List[str] = None,
    mode: str = 'check',
    polling_time: int = 60
) -> None:
    """
    按指定日期参数循环执行验证任务
    
    类似于 time_task_do_ztb 的实现方式
    """
```

---

## 四、调用方式对比

### 4.1 方式1: 脚本调用（保持兼容）

```bash
# 命令行参数
python tools/data_validation/data_validator.py \
    -s 20260422 \
    -e 20260422 \
    -t news \
    -m check

# JSON参数（新支持）
python tools/data_validation/data_validator.py \
    --params '{
        "start_date": "20260422",
        "end_date": "20260422",
        "validator_types": ["news"],
        "mode": "check"
    }'

# YAML任务（新支持）
python tools/data_validation/data_validator.py \
    --yaml-config config/validation_tasks.yaml \
    --task daily_news_validation

# 批量任务组（新支持）
python tools/data_validation/data_validator.py \
    --yaml-config config/validation_tasks.yaml \
    --batch-group daily_all
```

### 4.2 方式2: 函数导入（推荐）

```python
# 基础调用
from tools.data_validation import run_validation

result = run_validation(
    start_date='20260422',
    end_date='20260422',
    validator_types=['news'],
    mode='check'
)

print(f"总记录数: {result['reports'][0].total_records}")
print(f"异常记录数: {result['reports'][0].invalid_count}")

# YAML任务调用
result = run_validation(
    yaml_config='config/validation_tasks.yaml',
    task_name='daily_news_validation'
)
```

### 4.3 方式3: 批量验证

```python
from tools.data_validation import batch_validate

result = batch_validate(
    date_list=['20260420', '20260421', '20260422'],
    validator_types=['news', 'ztb'],
    mode='fix',
    auto_fix=True
)
```

### 4.4 方式4: 定时任务

```python
from tools.data_validation import time_task_do_validation

# 持续轮询验证
time_task_do_validation(
    date_param='2026-04-22',
    start_date='2026-04-22',
    end_date='2026-04-22',
    validator_types=['news'],
    mode='check',
    polling_time=300  # 每5分钟检查一次
)
```

---

## 五、参数对象设计

### 5.1 ValidationParams 数据类

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ValidationParams:
    """验证参数"""
    start_date: str                    # 开始日期 (YYYYMMDD)
    end_date: str                      # 结束日期 (YYYYMMDD)
    validator_types: List[str] = None  # 验证类型列表，None表示全部
    mode: str = 'check'                # 执行模式
    output_dir: str = './reports'      # 报告输出目录
    config_path: str = None            # 配置文件路径
    auto_fix: bool = False             # 是否自动修复
    interactive: bool = False          # 是否交互模式
    
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
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ValidationParams':
        import json
        return cls.from_dict(json.loads(json_str))
```

---

## 六、YAML配置加载器

```python
# tools/data_validation/yaml_loader.py

"""YAML配置加载器"""
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("请安装PyYAML: pip install pyyaml")

from .params import ValidationParams


class YamlConfigLoader:
    """YAML配置加载器"""
    
    # 变量映射
    VARIABLE_MAP = {
        'TODAY': lambda: datetime.now().strftime('%Y%m%d'),
        'YESTERDAY': lambda: (datetime.now() - timedelta(days=1)).strftime('%Y%m%d'),
        'TOMORROW': lambda: (datetime.now() + timedelta(days=1)).strftime('%Y%m%d'),
        'WEEK_AGO': lambda: (datetime.now() - timedelta(days=7)).strftime('%Y%m%d'),
        'MONTH_AGO': lambda: (datetime.now() - timedelta(days=30)).strftime('%Y%m%d'),
    }
    
    def __init__(self, yaml_path: str):
        self.yaml_path = yaml_path
        self.config = self._load_yaml()
    
    def _load_yaml(self) -> Dict:
        """加载YAML文件"""
        with open(self.yaml_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _resolve_variables(self, value: Any) -> Any:
        """解析变量"""
        if isinstance(value, str):
            # 替换 ${VAR} 格式的变量
            pattern = r'\$\{(\w+)\}'
            
            def replace_var(match):
                var_name = match.group(1)
                
                # 1. 检查是否是内置变量
                if var_name in self.VARIABLE_MAP:
                    return self.VARIABLE_MAP[var_name]()
                
                # 2. 检查环境变量
                env_value = os.getenv(var_name)
                if env_value is not None:
                    return env_value
                
                # 3. 保持原样
                return match.group(0)
            
            return re.sub(pattern, replace_var, value)
        
        elif isinstance(value, list):
            return [self._resolve_variables(item) for item in value]
        
        elif isinstance(value, dict):
            return {k: self._resolve_variables(v) for k, v in value.items()}
        
        return value
    
    def get_task(self, task_name: str) -> ValidationParams:
        """获取任务配置"""
        tasks = self.config.get('tasks', [])
        
        for task in tasks:
            if task.get('name') == task_name:
                if not task.get('enabled', True):
                    raise ValueError(f"任务 '{task_name}' 已被禁用")
                
                # 解析变量
                params_dict = self._resolve_variables(task.get('params', {}))
                
                # 合并全局配置
                global_config = self.config.get('global', {})
                if 'output_dir' not in params_dict and 'output_dir' in global_config:
                    params_dict['output_dir'] = global_config['output_dir']
                if 'validation_config' not in params_dict and 'validation_config' in global_config:
                    params_dict['config_path'] = global_config['validation_config']
                
                return ValidationParams.from_dict(params_dict)
        
        raise ValueError(f"找不到任务 '{task_name}'")
    
    def get_enabled_tasks(self) -> List[str]:
        """获取所有启用的任务名称"""
        tasks = self.config.get('tasks', [])
        return [t['name'] for t in tasks if t.get('enabled', True)]
    
    def get_batch_group(self, group_name: str) -> List[str]:
        """获取批量任务组中的任务列表"""
        groups = self.config.get('batch_groups', [])
        
        for group in groups:
            if group.get('name') == group_name:
                return group.get('tasks', [])
        
        raise ValueError(f"找不到批量任务组 '{group_name}'")
    
    def get_scheduled_tasks(self) -> List[Dict]:
        """获取配置了定时调度的任务"""
        tasks = self.config.get('tasks', [])
        return [t for t in tasks if t.get('enabled', True) and 'schedule' in t]
```

---

## 七、实施计划

| 步骤 | 任务 | 文件 | 预计时间 |
|------|------|------|----------|
| 1 | 创建 params.py 参数类 | params.py | 15分钟 |
| 2 | 创建 yaml_loader.py | yaml_loader.py | 30分钟 |
| 3 | 重构 data_validator.py | data_validator.py | 45分钟 |
| 4 | 创建 validation_tasks.yaml | config/validation_tasks.yaml | 15分钟 |
| 5 | 更新 __init__.py 导出 | __init__.py | 5分钟 |
| 6 | 测试函数调用 | - | 15分钟 |
| 7 | 测试YAML配置 | - | 15分钟 |
| **总计** | | | **140分钟** |

---

## 八、实施状态

- [x] 整体架构设计
- [x] YAML配置文件设计
- [x] 函数接口设计
- [x] YAML配置加载器设计
- [x] 实施计划制定
- [ ] 用户审核
- [ ] 代码实施
