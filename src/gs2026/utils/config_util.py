"""
配置工具模块

简单实用的配置管理，从 YAML 文件读取配置。
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml


# 默认编码
ENCODING_UTF8 = "utf-8"

# 配置缓存
_config_cache: Optional[Dict[str, Any]] = None
_config_path: Optional[Path] = None


def get_project_root() -> Path:
    """获取项目根目录"""
    current = Path(__file__).absolute()
    for parent in current.parents:
        if any((parent / marker).exists() for marker in [".git", "pyproject.toml", "setup.py"]):
            return parent
    return current.parent.parent.parent


def find_config_file(filename: str = "settings.yaml") -> Optional[Path]:
    """查找配置文件"""
    paths = [
        Path(filename),
        Path("configs") / filename,
        get_project_root() / "configs" / filename,
        get_project_root() / filename,
    ]
    for path in paths:
        if path.exists():
            return path
    return None


def load_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径，None 则自动查找
        
    Returns:
        配置字典
    """
    global _config_cache, _config_path
    
    if config_path:
        path = Path(config_path)
    else:
        path = find_config_file()
    
    if path is None or not path.exists():
        return {}
    
    with open(path, "r", encoding=ENCODING_UTF8) as f:
        _config_cache = yaml.safe_load(f) or {}
    
    _config_path = path
    return _config_cache


def get_config(
    key: str,
    default: Any = None,
    config_path: Optional[Union[str, Path]] = None
) -> Any:
    """
    获取配置值
    
    优先级: 环境变量 > 配置文件 > 默认值
    
    Args:
        key: 配置键，支持点号分隔如 "database.host"
        default: 默认值
        config_path: 指定配置文件路径
        
    Returns:
        配置值
        
    Example:
        >>> db_host = get_config("database.host", "localhost")
        >>> port = get_config("database.port", 3306)
    """
    global _config_cache
    
    # 1. 检查环境变量
    env_key = f"GS2026_{key.upper().replace('.', '_')}"
    env_value = os.getenv(env_key)
    if env_value is not None:
        return env_value
    
    # 2. 加载配置
    if _config_cache is None or config_path:
        load_config(config_path)
    
    # 3. 获取嵌套值
    if _config_cache is None:
        return default
    
    keys = key.split(".")
    value = _config_cache
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    
    return value if value is not None else default


def get_str(key: str, default: str = "") -> str:
    """获取字符串配置"""
    value = get_config(key, default)
    return str(value) if value is not None else default


def get_int(key: str, default: int = 0) -> int:
    """获取整数配置"""
    value = get_config(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    """获取布尔配置"""
    value = get_config(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


def get_list(key: str, default: Optional[list] = None) -> list:
    """获取列表配置"""
    value = get_config(key, default or [])
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [item.strip() for item in value.split(",")]
    return [value]


def reload_config() -> None:
    """重新加载配置"""
    global _config_cache
    _config_cache = None
    load_config()


# 便捷访问
class Config:
    """配置快捷访问类"""
    
    @staticmethod
    def db_host() -> str:
        return get_str("database.host", "192.168.0.101")
    
    @staticmethod
    def db_port() -> int:
        return get_int("database.port", 3306)
    
    @staticmethod
    def db_name() -> str:
        return get_str("database.name", "gs")
    
    @staticmethod
    def redis_host() -> str:
        return get_str("redis.host", "localhost")
    
    @staticmethod
    def redis_port() -> int:
        return get_int("redis.port", 6379)
    
    @staticmethod
    def debug() -> bool:
        return get_bool("app.debug", False)


# 导出
cfg = Config()


# ========== 测试代码 ==========

if __name__ == "__main__":
    """测试配置工具"""
    
    print("=" * 60)
    print("配置工具测试")
    print("=" * 60)
    
    # 1. 测试项目根目录查找
    print("\n1. 项目根目录:")
    root = get_project_root()
    print(f"   {root}")
    
    # 2. 测试配置文件查找
    print("\n2. 配置文件查找:")
    config_file = find_config_file("settings.yaml")
    if config_file:
        print(f"   找到: {config_file}")
    else:
        print("   未找到 settings.yaml")
    
    # 3. 测试加载配置
    print("\n3. 加载配置:")
    config_data = load_config()
    if config_data:
        print(f"   配置项数量: {len(config_data)}")
        print(f"   配置内容: {config_data}")
    else:
        print("   配置为空或文件不存在")
    
    # 4. 测试获取配置
    print("\n4. 获取配置值:")
    test_keys = [
        "common.url",
        "common.mysql_ip",
        "redis.host",
        "redis.port",
    ]
    for key in test_keys:
        value = get_config(key, "[默认值]")
        print(f"   {key}: {value}")
    
    # 5. 测试类型化获取
    print("\n5. 类型化获取:")
    print(f"   get_str('common.url'): {get_str('common.url', 'localhost')}")
    print(f"   get_int('redis.port'): {get_int('redis.port', 6379)}")
    # print(f"   get_bool('app.debug'): {get_bool('app.debug', False)}")
    # print(f"   get_list('app.sources'): {get_list('app.sources', ['akshare'])}")
    
    # 6. 测试快捷访问
    # print("\n6. 快捷访问 (cfg):")
    # print(f"   cfg.db_host(): {cfg.db_host()}")
    # print(f"   cfg.db_port(): {cfg.db_port()}")
    # print(f"   cfg.db_name(): {cfg.db_name()}")
    # print(f"   cfg.debug(): {cfg.debug()}")
    
    # 7. 测试环境变量覆盖
    # print("\n7. 环境变量覆盖测试:")
    # print("   设置环境变量: GS2026_DATABASE_HOST=test_host")
    # os.environ["GS2026_DATABASE_HOST"] = "test_host"
    # reload_config()  # 清除缓存
    # value = get_config("database.host", "localhost")
    # print(f"   get_config('database.host'): {value}")
    # del os.environ["GS2026_DATABASE_HOST"]  # 清理
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
