# 配置表集中管理方案

## 核心设计

### 理念
- **configs/settings.yaml**：只存非敏感配置（数据库连接地址、Redis地址、功能开关等）
- **数据库配置表**：统一存敏感配置（密码、Token、API密钥等），支持历史版本

### 配置表结构

```sql
-- 主配置表
CREATE TABLE sys_config (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    config_key VARCHAR(100) NOT NULL COMMENT '配置键，如: db_password, github_token',
    config_value TEXT COMMENT '配置值（加密存储）',
    config_type VARCHAR(20) DEFAULT 'string' COMMENT '类型: string, int, float, json, bool',
    category VARCHAR(50) DEFAULT 'general' COMMENT '分类: database, api, security, feature',
    description VARCHAR(500) COMMENT '配置说明',
    is_sensitive TINYINT(1) DEFAULT 0 COMMENT '是否敏感（1=是，需要加密）',
    is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(50) COMMENT '创建人',
    updated_by VARCHAR(50) COMMENT '更新人',
    
    UNIQUE KEY uk_key (config_key),
    KEY idx_category (category),
    KEY idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统配置表';

-- 配置历史表（记录变更）
CREATE TABLE sys_config_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    config_key VARCHAR(100) NOT NULL,
    config_value TEXT COMMENT '当时的配置值',
    operation VARCHAR(20) COMMENT '操作: CREATE, UPDATE, DELETE',
    operated_by VARCHAR(50) COMMENT '操作人',
    operated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_reason VARCHAR(500) COMMENT '变更原因',
    
    KEY idx_key_time (config_key, operated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='配置历史表';
```

### 敏感配置加密

```python
# src/gs2026/utils/config_encryption.py
"""配置加密工具"""
from cryptography.fernet import Fernet
import os

# 从环境变量读取加密密钥（服务器上设置，不提交到代码）
# export CONFIG_ENCRYPTION_KEY="your-32-byte-key-here"
ENCRYPTION_KEY = os.getenv('CONFIG_ENCRYPTION_KEY')

def encrypt_value(value: str) -> str:
    """加密配置值"""
    if not ENCRYPTION_KEY:
        raise ValueError("CONFIG_ENCRYPTION_KEY 未设置")
    f = Fernet(ENCRYPTION_KEY.encode())
    return f.encrypt(value.encode()).decode()

def decrypt_value(encrypted: str) -> str:
    """解密配置值"""
    if not ENCRYPTION_KEY:
        raise ValueError("CONFIG_ENCRYPTION_KEY 未设置")
    f = Fernet(ENCRYPTION_KEY.encode())
    return f.decrypt(encrypted.encode()).decode()
```

### 配置管理类

```python
# src/gs2026/utils/config_manager.py
"""统一配置管理器"""
import json
from typing import Any, Optional
from datetime import datetime
from gs2026.utils.mysql_util import MySQLUtil
from gs2026.utils.config_encryption import encrypt_value, decrypt_value

class ConfigManager:
    """配置管理器 - 从数据库读取配置，支持历史版本"""
    
    _instance = None
    _cache = {}
    _cache_time = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.mysql = MySQLUtil()
    
    def get(self, key: str, default: Any = None, use_cache: bool = True) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            use_cache: 是否使用缓存
        """
        # 检查缓存
        if use_cache and key in self._cache:
            cache_age = (datetime.now() - self._cache_time.get(key, datetime.now())).seconds
            if cache_age < 300:  # 缓存5分钟
                return self._cache[key]
        
        # 从数据库读取
        sql = """
            SELECT config_value, config_type, is_sensitive 
            FROM sys_config 
            WHERE config_key = %s AND is_active = 1
        """
        result = self.mysql.safe_read_sql(self.mysql.engine, sql, params=(key,))
        
        if result.empty:
            return default
        
        row = result.iloc[0]
        value = row['config_value']
        
        # 解密敏感配置
        if row['is_sensitive'] and value:
            value = decrypt_value(value)
        
        # 类型转换
        value = self._convert_type(value, row['config_type'])
        
        # 更新缓存
        if use_cache:
            self._cache[key] = value
            self._cache_time[key] = datetime.now()
        
        return value
    
    def set(self, key: str, value: Any, 
            config_type: str = 'string',
            category: str = 'general',
            description: str = '',
            is_sensitive: bool = False,
            user: str = 'system',
            reason: str = '') -> bool:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
            config_type: 类型
            category: 分类
            description: 说明
            is_sensitive: 是否敏感
            user: 操作人
            reason: 变更原因
        """
        # 检查是否已存在
        check_sql = "SELECT id FROM sys_config WHERE config_key = %s"
        exists = not self.mysql.safe_read_sql(self.mysql.engine, check_sql, params=(key,)).empty
        
        # 加密敏感值
        store_value = value
        if is_sensitive and value:
            store_value = encrypt_value(str(value))
        
        if exists:
            # 更新前记录历史
            old_value = self.get(key, use_cache=False)
            self._save_history(key, old_value, 'UPDATE', user, reason)
            
            # 更新
            sql = """
                UPDATE sys_config SET
                    config_value = %s,
                    config_type = %s,
                    category = %s,
                    description = %s,
                    is_sensitive = %s,
                    updated_by = %s
                WHERE config_key = %s
            """
            self.mysql.execute(sql, (store_value, config_type, category, 
                                   description, is_sensitive, user, key))
        else:
            # 新增
            sql = """
                INSERT INTO sys_config 
                (config_key, config_value, config_type, category, description, 
                 is_sensitive, created_by, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            self.mysql.execute(sql, (key, store_value, config_type, category,
                                   description, is_sensitive, user, user))
            self._save_history(key, None, 'CREATE', user, reason)
        
        # 清除缓存
        self._cache.pop(key, None)
        return True
    
    def get_history(self, key: str, limit: int = 10) -> list:
        """获取配置历史版本"""
        sql = """
            SELECT config_value, operation, operated_by, operated_at, change_reason
            FROM sys_config_history
            WHERE config_key = %s
            ORDER BY operated_at DESC
            LIMIT %s
        """
        result = self.mysql.safe_read_sql(self.mysql.engine, sql, params=(key, limit))
        return result.to_dict('records') if not result.empty else []
    
    def get_by_category(self, category: str) -> dict:
        """按分类获取所有配置"""
        sql = """
            SELECT config_key, config_value, config_type, is_sensitive, description
            FROM sys_config
            WHERE category = %s AND is_active = 1
        """
        result = self.mysql.safe_read_sql(self.mysql.engine, sql, params=(category,))
        
        configs = {}
        for _, row in result.iterrows():
            value = row['config_value']
            if row['is_sensitive'] and value:
                value = decrypt_value(value)
            configs[row['config_key']] = self._convert_type(value, row['config_type'])
        
        return configs
    
    def _convert_type(self, value: str, config_type: str) -> Any:
        """类型转换"""
        if value is None:
            return None
        
        if config_type == 'int':
            return int(value)
        elif config_type == 'float':
            return float(value)
        elif config_type == 'bool':
            return value.lower() in ('true', '1', 'yes', 'on')
        elif config_type == 'json':
            return json.loads(value)
        else:
            return str(value)
    
    def _save_history(self, key: str, value: Any, operation: str, 
                     user: str, reason: str):
        """保存历史记录"""
        sql = """
            INSERT INTO sys_config_history
            (config_key, config_value, operation, operated_by, change_reason)
            VALUES (%s, %s, %s, %s, %s)
        """
        self.mysql.execute(sql, (key, str(value) if value else None, 
                               operation, user, reason))

# 全局配置管理器实例
config_mgr = ConfigManager()

# 便捷函数
def get_config(key: str, default: Any = None) -> Any:
    """获取配置"""
    return config_mgr.get(key, default)

def set_config(key: str, value: Any, **kwargs) -> bool:
    """设置配置"""
    return config_mgr.set(key, value, **kwargs)
```

### 配置文件（简化版）

```yaml
# configs/settings.yaml（提交到 GitHub，无敏感信息）
# 只存连接地址、功能开关等非敏感配置

# 数据库连接（只存地址，密码从配置表读取）
database:
  host: "192.168.0.101"
  port: 3306
  user: "root"
  # password: 从 sys_config 表读取 (key: db_password)
  name: "gs"

# Redis（只存地址，密码从配置表读取）
redis:
  host: "192.168.0.101"
  port: 6379
  # password: 从 sys_config 表读取 (key: redis_password)

# 功能开关（非敏感，可直接存这里）
features:
  enable_anomaly_detection: true
  enable_auto_report: true
  max_concurrent_tasks: 10

# 日志配置（非敏感）
logging:
  level: "INFO"
  file_path: "logs/app.log"
```

### 初始化数据

```sql
-- 初始化敏感配置（通过 SQL 或管理界面录入）
INSERT INTO sys_config (config_key, config_value, config_type, category, 
                        description, is_sensitive) VALUES
('db_password', '加密后的密码', 'string', 'database', 
 '数据库密码', 1),
('redis_password', '加密后的密码', 'string', 'database', 
 'Redis密码', 1),
('github_token', '加密后的token', 'string', 'security', 
 'GitHub访问Token', 1),
('deepseek_api_key', '加密后的key', 'string', 'api', 
 'DeepSeek API密钥', 1),
('volcengine_api_key', '加密后的key', 'string', 'api', 
 '火山引擎API密钥', 1);
```

### 管理界面（Web）

```python
# 配置管理 API
@admin_bp.route('/api/configs', methods=['GET'])
def list_configs():
    """列出所有配置"""
    category = request.args.get('category')
    if category:
        configs = config_mgr.get_by_category(category)
    else:
        # 从数据库查询所有
        sql = "SELECT config_key, config_type, category, description, is_sensitive FROM sys_config WHERE is_active = 1"
        configs = mysql_util.safe_read_sql(mysql_util.engine, sql).to_dict('records')
    return jsonify({'success': True, 'items': configs})

@admin_bp.route('/api/configs/<key>', methods=['GET', 'PUT', 'POST'])
def manage_config(key):
    """获取/更新配置"""
    if request.method == 'GET':
        value = config_mgr.get(key)
        history = config_mgr.get_history(key, limit=5)
        return jsonify({'success': True, 'value': value, 'history': history})
    
    elif request.method in ('PUT', 'POST'):
        data = request.json
        config_mgr.set(
            key=key,
            value=data['value'],
            config_type=data.get('type', 'string'),
            category=data.get('category', 'general'),
            description=data.get('description', ''),
            is_sensitive=data.get('is_sensitive', False),
            user=current_user.username,  # 假设有用户系统
            reason=data.get('reason', '手动更新')
        )
        return jsonify({'success': True})
```

## 优势对比

| 特性 | 原方案（文件） | 新方案（配置表） |
|------|---------------|----------------|
| 敏感信息安全 | ❌ 明文存文件 | ✅ 加密存数据库 |
| 历史版本 | ❌ 无 | ✅ 自动记录 |
| 变更审计 | ❌ 无 | ✅ 记录操作人/时间/原因 |
| 动态更新 | ❌ 需重启 | ✅ 实时生效（带缓存） |
| 多环境管理 | ❌ 多个文件 | ✅ 同一套代码，不同配置值 |
| 权限控制 | ❌ 文件权限 | ✅ 数据库权限 + 界面控制 |
| 配置分类 | ❌ 无 | ✅ 按 category 分类 |

## 实施步骤

1. [ ] 创建配置表 SQL
2. [ ] 实现 ConfigManager 类
3. [ ] 实现加密工具
4. [ ] 迁移现有敏感配置到数据库
5. [ ] 简化 settings.yaml（删除敏感信息）
6. [ ] 修改代码使用新的配置读取方式
7. [ ] （可选）开发 Web 管理界面

审核通过后实施。