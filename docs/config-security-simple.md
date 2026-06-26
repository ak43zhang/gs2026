# 配置文件敏感信息处理方案

## 核心问题
- `configs/settings.yaml` 包含数据库密码、API密钥等敏感信息
- 提交到 GitHub 会泄露
- 不提交则新环境缺少配置文件无法运行

## 简单解决方案：模板 + 本地覆盖

### 方案设计

```
configs/
├── settings.yaml.template    # 提交到 GitHub（模板，无真实密码）
├── settings.yaml             # 不提交（本地真实配置，.gitignore）
└── settings.yaml.example     # 示例文件（可选，帮助理解）
```

### 具体实施

#### 1. 创建模板文件（提交到 GitHub）

```yaml
# configs/settings.yaml.template
# 配置文件模板 - 复制为 settings.yaml 并填写真实值

database:
  host: "192.168.0.101"
  port: 3306
  user: "root"
  password: "${DB_PASSWORD}"  # 从环境变量读取，或手动填写
  name: "gs"

redis:
  host: "192.168.0.101"
  port: 6379
  password: "${REDIS_PASSWORD}"  # 从环境变量读取

github:
  token: "${GITHUB_TOKEN}"  # 从环境变量读取

api_keys:
  deepseek: "${DEEPSEEK_KEY}"
  volcengine: "${VOLCENGINE_KEY}"
```

#### 2. 更新 .gitignore

```gitignore
# 敏感配置文件
configs/settings.yaml
configs/*.local.yaml
.env
```

#### 3. 修改配置加载代码

```python
# src/gs2026/utils/config_util.py

import os
import yaml
from pathlib import Path

# 尝试从环境变量读取，否则返回空字符串
def _get_env_or_empty(key):
    return os.getenv(key, "")

def load_config():
    """加载配置，支持环境变量覆盖"""
    config_path = Path(__file__).parent.parent.parent.parent / "configs" / "settings.yaml"
    
    if not config_path.exists():
        # 如果本地配置不存在，从模板创建
        template_path = config_path.with_suffix(".yaml.template")
        if template_path.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {config_path}\n"
                f"请复制模板文件: cp configs/settings.yaml.template configs/settings.yaml\n"
                f"然后填写真实密码"
            )
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 替换环境变量占位符 ${VAR_NAME}
    import re
    def replace_env_var(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))  # 如果环境变量不存在，保留原样
    
    content = re.sub(r'\$\{(\w+)\}', replace_env_var, content)
    
    config = yaml.safe_load(content)
    return config

# 全局配置对象
cfg = load_config()
```

#### 4. 首次使用流程

```bash
# 1. 克隆仓库后，复制模板
cp configs/settings.yaml.template configs/settings.yaml

# 2. 编辑 settings.yaml，填写真实密码
# 方法A：直接编辑文件（适合本地开发）
# 方法B：使用环境变量（适合服务器）

# 方法B示例：
export DB_PASSWORD="123456"
export GITHUB_TOKEN="ghp_xxxx"
```

### 对比方案

| 方案 | 复杂度 | 安全性 | 适用场景 |
|------|--------|--------|----------|
| **模板+本地** | 低 | 中 | 当前项目（推荐） |
| 环境变量完全替代 | 中 | 高 | 服务器部署 |
| 加密存储 | 高 | 高 | 高安全要求 |

### 推荐：模板+本地 方案

**优点：**
- 简单，改动小
- 不依赖外部服务
- 开发体验好（有文件可查看）
- 不会误提交敏感信息

**缺点：**
- 需要手动复制模板
- 多人协作时需各自维护本地配置

### 额外保护：提交前检查

```bash
# .git/hooks/pre-commit（可选）
#!/bin/bash
if git diff --cached --name-only | grep -E "configs/settings\.yaml$"; then
    echo "ERROR: 试图提交 settings.yaml，请确认不包含敏感信息"
    echo "如果确实需要提交，使用: git commit --no-verify"
    exit 1
fi
```

## 实施步骤

1. [ ] 创建 `settings.yaml.template`
2. [ ] 更新 `.gitignore`
3. [ ] 修改 `config_util.py` 支持环境变量替换
4. [ ] 删除 Git 历史中的 `settings.yaml`（如果已提交过）
5. [ ] 本地复制模板并填写真实配置

审核通过后实施。