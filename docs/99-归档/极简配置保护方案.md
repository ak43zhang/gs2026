# 极简配置保护方案

## 核心思路
**本地加密文件 + 自动解密使用**

既不用改代码，也不用手动解密，像普通文件一样方便。

---

## 方案设计

### 1. 文件结构

```
configs/
├── settings.yaml              # 普通配置（提交GitHub）
├── secrets.yaml.enc          # 敏感配置（加密后提交GitHub）
└── secrets.yaml              # 敏感配置（本地明文，不提交）
```

### 2. 使用方式

**日常开发（自动处理）：**
```python
# 代码里这样用（和原来一样）
from gs2026.utils.config_util import cfg
volc_key = cfg['volcengine']['api_key']  # 自动解密
```

**加密提交（一键脚本）：**
```bash
# 修改完敏感配置后，一键加密提交
python encrypt_secrets.py
# 输入密码 → 自动生成 secrets.yaml.enc → 提交
```

### 3. 具体实现

#### encrypt_secrets.py（加密脚本）

```python
#!/usr/bin/env python3
"""一键加密敏感配置"""
from cryptography.fernet import Fernet
import getpass
import os

# 从环境变量或输入获取加密密码
ENCRYPT_PWD = os.getenv('SECRETS_PWD') or getpass.getpass('输入加密密码: ')

def encrypt():
    # 生成密钥
    key = Fernet.generate_key()
    
    # 读取明文配置
    with open('configs/secrets.yaml', 'rb') as f:
        data = f.read()
    
    # 加密
    f = Fernet(key)
    encrypted = f.encrypt(data)
    
    # 保存加密文件
    with open('configs/secrets.yaml.enc', 'wb') as f:
        f.write(encrypted)
    
    # 保存密钥（用户自己保管，不提交）
    with open('.secrets_key', 'wb') as f:
        f.write(key)
    
    print('✅ 已加密: configs/secrets.yaml.enc')
    print('✅ 密钥保存: .secrets_key (请备份，勿提交)')
    print('提示: git add configs/secrets.yaml.enc')

def decrypt():
    # 读取密钥
    with open('.secrets_key', 'rb') as f:
        key = f.read()
    
    # 读取加密文件
    with open('configs/secrets.yaml.enc', 'rb') as f:
        encrypted = f.read()
    
    # 解密
    f = Fernet(key)
    data = f.decrypt(encrypted)
    
    # 保存明文
    with open('configs/secrets.yaml', 'wb') as f:
        f.write(data)
    
    print('✅ 已解密: configs/secrets.yaml')

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'decrypt':
        decrypt()
    else:
        encrypt()
```

#### 修改 config_util.py（自动解密）

```python
# 在原有代码基础上添加

def _load_secrets():
    """加载加密配置，自动解密"""
    secrets_path = Path(__file__).parent.parent.parent.parent / "configs" / "secrets.yaml"
    enc_path = secrets_path.with_suffix('.yaml.enc')
    key_path = Path(__file__).parent.parent.parent.parent / ".secrets_key"
    
    # 明文存在直接读
    if secrets_path.exists():
        with open(secrets_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    # 明文不存在，尝试解密
    if enc_path.exists() and key_path.exists():
        from cryptography.fernet import Fernet
        with open(key_path, 'rb') as f:
            key = f.read()
        with open(enc_path, 'rb') as f:
            encrypted = f.read()
        
        f = Fernet(key)
        data = f.decrypt(encrypted)
        
        # 保存明文供使用
        with open(secrets_path, 'wb') as f:
            f.write(data)
        
        return yaml.safe_load(data) or {}
    
    return {}

# 合并配置
_cfg_secrets = _load_secrets()
cfg = {**_cfg_normal, **_cfg_secrets}  # secrets 覆盖普通配置
```

### 4. 配置文件示例

```yaml
# configs/settings.yaml（提交GitHub）
# 普通配置，不敏感
database:
  host: "192.168.0.101"
  port: 3306
  user: "root"
  # 密码在 secrets.yaml

features:
  enable_monitor: true
```

```yaml
# configs/secrets.yaml（本地使用，加密后提交）
# 敏感配置
volcengine:
  api_key: "31j6ncHEpvHhPsK9t6KmBzNRdczEPK4rxSjPPDRr6C1XlHtYhcQy4vdhC7aUKWzi7"
  ark_key: "ark-3ac330c7-cea0-4bdf-9ce5-6c1cdbee4d54-cf489"

deepseek:
  api_key: "sk-..."

database:
  password: "123456"
```

### 5. .gitignore

```gitignore
# 明文敏感配置（不提交）
configs/secrets.yaml
.secrets_key

# 其他敏感文件
.env
*.pem
```

### 6. 使用流程

**首次设置（2分钟）：**
```bash
# 1. 创建敏感配置
cat > configs/secrets.yaml << 'EOF'
volcengine:
  api_key: "你的真实key"
EOF

# 2. 加密
python encrypt_secrets.py
# 输入密码

# 3. 提交加密文件
git add configs/secrets.yaml.enc
git commit -m "添加加密配置"
```

**日常使用（无感知）：**
```python
# 代码里正常使用
volc_key = cfg['volcengine']['api_key']  # 自动可用
```

**换电脑/重装（恢复）：**
```bash
# 1. 克隆仓库
git clone ...

# 2. 复制密钥文件（从备份/U盘/邮件）
cp /backup/.secrets_key ./

# 3. 自动解密（运行任意代码时自动完成）
# 或手动: python encrypt_secrets.py decrypt
```

---

## 方案对比

| 方案 | 复杂度 | 安全性 | 方便性 | 防丢失 |
|------|--------|--------|--------|--------|
| 环境变量 | 中 | 高 | 低 | 差 |
| 数据库配置表 | 高 | 高 | 中 | 好 |
| **本方案（加密文件）** | **低** | **高** | **高** | **好** |

## 优势

1. **简单**：只加一个文件 + 一个脚本
2. **方便**：代码使用方式完全不变
3. **安全**：GitHub 上是加密内容
4. **防丢失**：加密文件在 GitHub，密钥自己备份
5. **自动**：运行代码时自动解密

审核通过后实施。