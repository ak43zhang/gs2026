"""
配置定位工具
从项目根目录自动查找 configs/huatai_trader/config.yaml
"""

from pathlib import Path
from typing import Optional

_CONFIG_REL_PATH = Path("configs") / "huatai_trader" / "config.yaml"
_cached_path: Optional[Path] = None


def find_config() -> Path:
    """
    自动定位配置文件，从当前文件向上查找项目根目录
    
    Returns:
        配置文件的绝对路径
        
    Raises:
        FileNotFoundError: 找不到配置文件
    """
    global _cached_path
    if _cached_path and _cached_path.exists():
        return _cached_path
    
    # 从当前文件位置向上查找
    current = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = current / _CONFIG_REL_PATH
        if candidate.exists():
            _cached_path = candidate
            return candidate
        current = current.parent
    
    raise FileNotFoundError(
        f"找不到配置文件 {_CONFIG_REL_PATH}\n"
        f"请确认 configs/huatai_trader/config.yaml 存在于项目根目录下"
    )


def get_project_root() -> Path:
    """获取项目根目录"""
    config_path = find_config()
    # config.yaml 在 configs/huatai_trader/ 下，往上2级就是项目根
    return config_path.parent.parent.parent


def load_config() -> dict:
    """加载并返回完整配置字典"""
    import yaml
    config_path = find_config()
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_path(relative_path: str) -> str:
    """将配置中的相对路径解析为绝对路径"""
    if not relative_path:
        return ""
    p = Path(relative_path)
    if p.is_absolute():
        return str(p)
    # 相对于项目根目录
    return str(get_project_root() / p)
