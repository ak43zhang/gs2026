# GitHub 账号安全方案设计

## 当前风险分析

### 潜在泄密途径
1. **硬编码凭证**：代码中直接包含 GitHub Token、密码等
2. **配置文件泄露**：`.env`、`config.yaml` 等包含敏感信息提交到仓库
3. **日志文件泄露**：日志中打印了 Token、密钥等
4. **历史提交记录**：即使删除，Git 历史仍可恢复
5. **本地缓存文件**：`.git/credentials`、IDE 缓存等

### 已发现的风险点
- `configs/settings.yaml` 包含 API 密钥
- 部分脚本文件包含数据库密码
- 日志可能打印敏感信息

---

## 方案设计：多层防护体系

### 第一层：代码层防护（预防）

#### 1.1 敏感信息扫描（Git Hook）
```bash
# .git/hooks/pre-commit
#!/bin/bash
# 扫描即将提交的代码中是否包含敏感信息

# 检查模式
PATTERNS=(
    "github[_-]?token"
    "ghp_[a-zA-Z0-9]{36}"  # GitHub Personal Access Token
    "gho_[a-zA-Z0-9]{36}"  # GitHub OAuth Token
    "api[_-]?key"
    "password\s*[=:]",
    "secret\s*[=:]"
    "AKIA[0-9A-Z]{16}"      # AWS Key
    "mysql://[^:]+:[^@]+@"  # MySQL 连接字符串
)

for pattern in "${PATTERNS[@]}"; do
    if git diff --cached | grep -iE "$pattern"; then
        echo "ERROR: 检测到敏感信息，提交被拒绝"
        exit 1
    fi
done
```

#### 1.2 配置文件模板化
```yaml
# configs/settings.yaml.template（提交到仓库）
database:
  host: "${DB_HOST}"
  port: "${DB_PORT}"
  user: "${DB_USER}"
  password: "${DB_PASSWORD}"  # 从环境变量读取

github:
  token: "${GITHUB_TOKEN}"  # 从环境变量读取

# configs/settings.yaml（本地文件，不提交到仓库）
# 添加到 .gitignore
```

#### 1.3 环境变量管理
```python
# src/gs2026/utils/config_util.py
import os
from dotenv import load_dotenv

# 加载 .env 文件（不提交到仓库）
load_dotenv('.env')

def get_sensitive_config(key, default=None):
    """从环境变量获取敏感配置"""
    return os.getenv(key, default)

# 使用示例
DB_PASSWORD = get_sensitive_config('DB_PASSWORD')
GITHUB_TOKEN = get_sensitive_config('GITHUB_TOKEN')
```

---

### 第二层：仓库层防护（检测）

#### 2.1 GitHub Secret Scanning（启用）
- 在仓库 Settings → Security → Secret scanning 中启用
- 自动检测提交的 Token、密钥等

#### 2.2 敏感文件检查（CI/CD）
```yaml
# .github/workflows/security-check.yml
name: Security Check

on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Scan for secrets
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: main
          head: HEAD
          extra_args: --debug --only-verified
      
      - name: Check for sensitive files
        run: |
          # 检查是否提交了 .env、config.yaml 等
          if git ls-files | grep -E "\.(env|pem|key)$"; then
            echo "ERROR: 检测到敏感文件"
            exit 1
          fi
      
      - name: Check for hardcoded credentials
        run: |
          # 扫描代码中的硬编码凭证
          grep -r "ghp_" src/ || true
          grep -r "password.*=" src/ || true
```

---

### 第三层：访问层防护（控制）

#### 3.1 GitHub Token 权限最小化
```
Token 类型：Fine-grained personal access token
权限设置：
  - Contents: Read and write（仅必要的仓库）
  - Metadata: Read
  - 不勾选其他权限
过期时间：30-90天
```

#### 3.2 双因素认证（2FA）
- 强制开启 2FA
- 使用 TOTP 或硬件密钥
- 不接收短信验证码

#### 3.3 部署密钥（Deploy Keys）
```bash
# 为服务器生成专用 SSH Key
ssh-keygen -t ed25519 -C "deploy@server" -f ~/.ssh/github_deploy

# 在仓库 Settings → Deploy keys 中添加公钥
# 仅授予 Read 或 Read/Write 权限

# 本地配置使用 Deploy Key
Host github-deploy
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_deploy
```

---

### 第四层：监控层防护（响应）

#### 4.1 异常访问告警
- GitHub Security → Audit log 监控
- 设置邮件/Slack 告警
- 监控 IP 地址、时间、操作类型

#### 4.2 Token 泄露应急响应
```bash
#!/bin/bash
# emergency-revoke.sh
# Token 疑似泄露时的紧急处理

# 1. 立即撤销 Token
curl -X DELETE \
  -H "Authorization: token $OLD_TOKEN" \
  https://api.github.com/applications/Iv1.../token

# 2. 生成新 Token
NEW_TOKEN=$(curl -X POST \
  -H "Authorization: Basic $(echo -n 'username:password' | base64)" \
  -d '{"scopes":["repo"],"note":"Emergency replacement"}' \
  https://api.github.com/authorizations | jq -r .token)

# 3. 更新服务器环境变量
# ...

# 4. 检查仓库是否被篡改
git log --oneline --since="24 hours ago"
```

---

## 实施步骤

### 阶段1：立即实施（高优先级）
1. [ ] 启用 GitHub Secret Scanning
2. [ ] 检查并撤销历史提交中的 Token
3. [ ] 将硬编码凭证迁移到环境变量
4. [ ] 创建 `.env.template` 和 `.gitignore`

### 阶段2：本周实施
1. [ ] 配置 pre-commit hook
2. [ ] 添加 CI/CD 安全扫描
3. [ ] 启用 2FA
4. [ ] 生成 Fine-grained Token 替换旧 Token

### 阶段3：持续维护
1. [ ] 定期轮换 Token（90天）
2. [ ] 审查 Access Log
3. [ ] 安全培训

---

## 具体实施代码

### 1. .gitignore 更新
```gitignore
# 敏感文件
.env
.env.local
.env.*.local
*.pem
*.key
*.p12
*.pfx

# 配置文件（实际配置从模板复制）
configs/settings.yaml
!configs/settings.yaml.template

# 日志
logs/
*.log

# IDE
.idea/
.vscode/settings.json
```

### 2. 环境变量模板
```bash
# .env.template（提交到仓库）
# 复制为 .env 并填写实际值

# Database
DB_HOST=192.168.0.101
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password_here

# GitHub
GITHUB_TOKEN=ghp_your_token_here

# API Keys
DEEPSEEK_API_KEY=your_key_here
VOLCENGINE_API_KEY=your_key_here
```

### 3. 配置加载工具
```python
# src/gs2026/utils/safe_config.py
"""安全配置加载，支持环境变量和加密存储"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
env_path = Path(__file__).parent.parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

class SafeConfig:
    """安全配置管理器"""
    
    @staticmethod
    def get(key, default=None, sensitive=False):
        """
        获取配置值
        
        Args:
            key: 环境变量名
            default: 默认值
            sensitive: 是否为敏感信息（日志中会脱敏）
        """
        value = os.getenv(key, default)
        
        if sensitive and value:
            # 脱敏显示
            masked = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '****'
            print(f"[Config] {key}={masked}")
        
        return value
    
    @staticmethod
    def get_db_url():
        """获取数据库连接字符串（安全方式）"""
        host = SafeConfig.get('DB_HOST', 'localhost')
        port = SafeConfig.get('DB_PORT', '3306')
        user = SafeConfig.get('DB_USER', 'root')
        password = SafeConfig.get('DB_PASSWORD', '', sensitive=True)
        database = SafeConfig.get('DB_NAME', 'gs')
        
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    
    @staticmethod
    def get_github_token():
        """获取 GitHub Token（安全方式）"""
        return SafeConfig.get('GITHUB_TOKEN', '', sensitive=True)

# 使用示例
# from gs2026.utils.safe_config import SafeConfig
# token = SafeConfig.get_github_token()
```

---

## 审核要点

1. **是否接受此方案设计？**
2. **是否需要调整实施优先级？**
3. **是否有其他敏感信息需要保护？**
4. **是否需要集成到现有 CI/CD 流程？**

审核通过后，按阶段实施。