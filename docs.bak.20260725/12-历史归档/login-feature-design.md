# GS2026 登录功能设计文档

> 版本: 1.0.0  
> 日期: 2026-05-09  
> 状态: 已实施

---

## 1. 设计原则

- 基于现有 MySQL `accounts` 表（`service_type='gs2026'`），支持多账号
- 功能独立，通过 `configs/settings.yaml` 的 `auth.enabled` 开关控制
- 启用时所有页面需要登录，禁用时完全透明
- Session 永不过期（可配置有效期天数）
- 前端风格与现有深色主题一致，简约

---

## 2. 账号存储

### 2.1 使用现有表

表名：`accounts`（已存在于 `gs` 数据库）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int AUTO_INCREMENT | 主键 |
| username | varchar(100) UNIQUE | 登录用户名 |
| password | varchar(500) | 密码哈希（pbkdf2:sha256） |
| service_type | varchar(50) | 固定 `'gs2026'` |
| is_locked | tinyint(1) | 账号锁定状态（预留） |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 2.2 筛选条件

登录时仅查询 `service_type = 'gs2026'` 且 `is_locked = 0` 的账号。

---

## 3. 配置开关

文件：`configs/settings.yaml`

```yaml
auth:
  enabled: true                # false 则完全禁用登录功能
  service_type: gs2026         # 账号筛选标识
  session_lifetime_days: 365   # session 有效期（天）
```

### 3.1 启用/禁用

- `auth.enabled: true` → 所有页面需要登录
- `auth.enabled: false` → 所有页面无需登录，完全透明

---

## 4. 后端实现

### 4.1 新增文件

- `src/gs2026/dashboard2/routes/auth.py` — 登录/登出路由蓝图

### 4.2 路由定义

| 路由 | 方法 | 说明 |
|------|------|------|
| `/login` | GET | 渲染登录页面 |
| `/login` | POST | 校验用户名密码 |
| `/logout` | GET | 清除 session，重定向到 /login |

### 4.3 app.py 修改

- 设置 `app.permanent_session_lifetime`
- 注册 `auth_bp` 蓝图
- 添加 `before_request` 钩子，检查 session

### 4.4 放行路径

`before_request` 钩子对以下路径放行：

- `/login`、`/logout` — 登录相关
- `/static/` — 静态资源

---

## 5. 前端实现

### 5.1 新增文件

- `src/gs2026/dashboard2/templates/login.html` — 登录页面

### 5.2 登录页设计

- 深色渐变背景（#1a1d29 → #2d3142）
- 居中卡片式表单，圆角阴影
- Logo 📊 + 标题 "GS2026"
- 用户名/密码输入框 + 登录按钮
- 错误提示条（红色边框）

### 5.3 退出按钮

所有页面导航栏右侧添加退出按钮（仅登录功能启用时显示）。

---

## 6. 密码工具

### 6.1 文件位置

`tools/auth_manager.py`

### 6.2 功能

```bash
python tools/auth_manager.py add <username> <password>   # 添加账号
python tools/auth_manager.py list                        # 列出所有账号
python tools/auth_manager.py reset <username> <new_pwd>  # 重置密码
python tools/auth_manager.py delete <username>           # 删除账号
```

---

## 7. 安全性

- 密码使用 `werkzeug.security` 的 `pbkdf2:sha256` 哈希
- Session cookie 使用 Flask SECRET_KEY 签名
- 登录失败统一提示"用户名或密码错误"
- 支持账号锁定（表结构预留，暂不实现）
- 零新增 Python 依赖

---

## 8. 影响范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `configs/settings.yaml` | 修改 | 新增 auth 配置段 |
| `src/gs2026/dashboard2/routes/auth.py` | 新增 | 登录/登出路由 |
| `src/gs2026/dashboard2/templates/login.html` | 新增 | 登录页面 |
| `src/gs2026/dashboard2/app.py` | 修改 | 注册蓝图 + before_request |
| `src/gs2026/dashboard2/templates/*.html` | 修改 | header 添加退出按钮 |
| `tools/auth_manager.py` | 新增 | 账号管理工具 |
| `docs/tools/README.md` | 修改 | 更新工具文档 |

---

## 9. 依赖

无新增 Python 包。使用 Flask 内置的：
- `flask.session` — session 管理
- `werkzeug.security` — 密码哈希

---

## 10. 回滚方案

将 `configs/settings.yaml` 中 `auth.enabled` 设为 `false` 即可完全禁用登录功能，无需删除任何代码。
