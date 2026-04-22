"""YAML配置加载器

使用示例:
    from tools.data_validation.yaml_loader import YamlConfigLoader
    
    loader = YamlConfigLoader('config/validation_tasks.yaml')
    params = loader.get_task('daily_news_validation')
"""
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("请安装PyYAML: pip install pyyaml")


class YamlConfigLoader:
    """YAML配置加载器"""
    
    # 内置变量映射
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
    
    def get_global_config(self) -> Dict:
        """获取全局配置"""
        return self.config.get('global', {})
    
    def get_task(self, task_name: str) -> Dict:
        """获取任务配置（返回字典）"""
        tasks = self.config.get('tasks', [])
        
        for task in tasks:
            if task.get('name') == task_name:
                if not task.get('enabled', True):
                    raise ValueError(f"任务 '{task_name}' 已被禁用")
                
                # 解析变量
                params_dict = self._resolve_variables(task.get('params', {}))
                
                # 合并全局配置
                global_config = self.get_global_config()
                if 'output_dir' not in params_dict and 'output_dir' in global_config:
                    params_dict['output_dir'] = global_config['output_dir']
                if 'validation_config' in global_config and 'config_path' not in params_dict:
                    params_dict['config_path'] = global_config['validation_config']
                
                return params_dict
        
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
