"""
开发环境设置脚本

自动将 src 目录添加到 Python 路径，使 from gs2026.xxx 可以正常工作。
在开发时运行: python setup_dev.py
"""

import sys
from pathlib import Path


def setup_dev_path():
    """设置开发环境路径"""
    # 获取项目根目录
    project_root = Path(__file__).parent.absolute()
    src_path = project_root / "src"
    
    # 将 src 目录添加到 Python 路径
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
        print(f"[OK] Added to PYTHONPATH: {src_path}")
    else:
        print(f"[INFO] Already in PYTHONPATH: {src_path}")
    
    # 验证导入
    try:
        from gs2026.utils.config_util import get_config
        print("[OK] Import test passed: gs2026.utils.config_util")
    except ImportError as e:
        print(f"[FAIL] Import test failed: {e}")
    
    return src_path


if __name__ == "__main__":
    setup_dev_path()
    print("\n[INFO] You can now use: from gs2026.xxx import yyy")
