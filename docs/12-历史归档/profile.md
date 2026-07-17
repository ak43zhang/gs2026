# GS2026 个人中心开发文档

> 版本: 2.0.0 (修复版)  
> 日期: 2026-05-10  
> 状态: ✅ 已完成

---

## 1. 概述

个人中心是 GS2026 的账号级功能模块，基于 MySQL `accounts` 表（`service_type='gs2026'`）做账号隔离。首期实现「工作日志」功能，后续可扩展。

### 1.1 功能列表

| 模块 | 状态 | 说明 |
|------|------|------|
| 日志 | ✅ 已完成 | 日历 + 日志内容 + 待办清单 + 备注 + 标签 + 心情 |
| 统计 | 🔲 预留 | 日志频率、标签统计 |
| 设置 | 🔲 预留 | 修改密码、偏好设置 |

---

## 2. 登录认证

### 2.1 账号存储

- 表名：`accounts`（`gs` 数据库）
- 筛选条件：`service_type = 'gs2026'`
- 密码：werkzeug `pbkdf2:sha256` 哈希
- 多账号支持

### 2.2 配置开关

```yaml
# configs/settings.yaml
auth:
  enabled: true        # false 则完全无感知禁用
  service_type: gs2026
  session_lifetime_days: 365  # 当前使用会话cookie（关闭浏览器即过期）
```

### 2.3 文件清单

| 文件 | 说明 |
|------|------|
| `src/gs2026/dashboard2/routes/auth.py` | 登录/登出路由 |
| `src/gs2026/dashboard2/templates/login.html` | 登录页面（深色主题） |
| `src/gs2026/dashboard2/app.py` | 注册蓝图 + before_request 拦截 |
| `tools/auth_manager.py` | 账号管理 CLI 工具 |
| `src/gs2026/dashboard2/static/css/pages.css` | 退出按钮靠右 CSS |

### 2.4 Session 策略

当前使用**会话 cookie**（`session.permanent = False`）：关闭浏览器需重新登录。切换为永久 cookie 需将 `session.permanent` 改为 `True`。

---

## 3. 日志功能

### 3.1 数据库表

```sql
CREATE TABLE user_journals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    journal_date DATE NOT NULL,
    content TEXT COMMENT '日志内容（N-gram 格式）',
    todo_items TEXT COMMENT '今日事项（JSON 数组 [{text, done}]）',
    remarks TEXT COMMENT '备注',
    tags VARCHAR(500) COMMENT '标签（逗号分隔）',
    mood VARCHAR(20) COMMENT '心情 emoji',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_date (username, journal_date),
    KEY idx_username (username),
    KEY idx_journal_date (journal_date)
);
```

### 3.2 数据格式

#### 日志内容（content）

纯文本，无固定格式，自由输入。

#### 今日事项（todo_items）→ JSON 数组

```json
[
  {"text": "完成个人中心功能开发", "done": true},
  {"text": "修复 emoji 存储问题", "done": true},
  {"text": "部署上线", "done": false}
]
```

- 兼容旧数据：非 JSON 按换行拆分为多条，全部 `done: false`
- 每人每天一条记录，`INSERT ... ON DUPLICATE KEY UPDATE`

#### 备注（remarks）

纯文本。

#### 标签（tags）

逗号分隔字符串，如 `"开发,功能,测试"`。

#### 心情（mood）

Emoji 字符串，如 `"😊"`、`"💪"`、`"😫"`。

---

### 3.3 API 路由

文件：`src/gs2026/dashboard2/routes/profile.py`

| 路由 | 方法 | 说明 |
|------|------|------|
| `/profile` | GET | 个人中心页面 |
| `/api/journal/get?date=YYYY-MM-DD` | GET | 获取指定日期日志 |
| `/api/journal/save` | POST | 保存/更新日志（json body） |
| `/api/journal/list?year=Y&month=M` | GET | 获取月份有日志的日期列表 |
| `/api/journal/delete` | POST | 删除指定日期日志 |

所有 API 从 `session['username']` 取用户，不通过前端传用户。

---

### 3.4 UI 流程

#### 日志展示模式

- 页面加载 → 默认选中今天 → 自动加载展示
- 日历点击 → 切换日期 → 加载该日日志
- 展示区：内容 + 待办清单(✅/○) + 备注 + 标签 + 心情
- **点击待办圆圈直接切换完成状态**，即时保存
- 所有字段始终展示，空值显示默认文本
- 点击「编辑」进入编辑模式

#### 日志编辑模式

- 顶部「← 返回查看」按钮
- 内容：大文本框（保持不变）
- 今日事项：列表 + 每条可编辑文本/切换完成/删除 + 底部添加新事项
- 备注：文本框
- 标签：输入框
- 心情：emoji 选择器
- 点击「保存日志」→ 保存成功自动切回展示模式

#### 日志新建

- 无日志的日期点击 → 直接进入编辑模式

### 3.5 前端文件

| 文件 | 说明 |
|------|------|
| `src/gs2026/dashboard2/templates/profile.html` | 个人中心完整页面 |

### 3.6 暖色背景

- 页面加载时从 8 种暖色渐变中随机选一个
- 暖阳/蜜桃/薄荷奶/奶茶/薰衣草/晚霞/樱花/天空
- 导航栏保持原有深色不变
- 卡片透明，暖色从 `.profile-layout` 透出
- CSS class `.warm-page` 适配所有组件的暖色样式

---

## 4. 导航栏改动

### 4.1 新增图标

导航栏从右到左：`[首页] ... [智能选股] [👤个人中心] [🚪退出]`

### 4.2 CSS

```css
.main-nav a.nav-profile-icon { margin-left: auto; }
```

### 4.3 受影响文件

12个页面模板的 `<nav>` 均添加了个人中心图标和退出按钮。

---

## 5. 开发历程 & Bug 修复记录

### 5.1 tick 数据归零 bug（2026-05-07）

- 根因：`pd.read_json()` 将纯数字 `bond_code` 解析为 `int64`，而 adata 来源为 `str`
- `set_index('code').reindex(string_codes)` 因类型不匹配全部 NaN → diff 全空 → `min_up=0`
- 修复：rename 后统一 `.astype(str)`

### 5.2 标签重命名（2026-05-07）

- 大盘概览标签：`↑涨↓跌` → `上涨家数/下跌家数/tick上涨数/tick下跌数/总数`
- 文件：`dashboard2/templates/monitor.html`

### 5.3 emoji 存储报错（2026-05-10）

- 根因：MySQL 连接 `charset=utf8` 不支持 4 字节 emoji
- 修复：profile.py 连接串替换为 `charset=utf8mb4`

### 5.4 JS 语法错误（2026-05-10）

- 根因：`applyWarmBackground` IIFE 后多了多余 `}`
- 修复：删除多余闭合括号

### 5.5 暖色不显示（2026-05-10）

- 根因：`showViewMode()` 中强制设置 `rgba(255,255,255,0.6)` 白色遮罩
- 修复：移除遮罩，section-card 改为 transparent

### 5.6 页面空白（2026-05-10）

- 根因：修改了不存在的 `initCalendar()` 函数位置
- 修复：改为修改已有的 `initCalendar()` 调用

---

## 6. 账号管理工具

文件：`tools/auth_manager.py`

```bash
# 添加账号
python tools/auth_manager.py add admin mypassword

# 列出所有账号
python tools/auth_manager.py list

# 重置密码
python tools/auth_manager.py reset admin newpassword

# 删除账号
python tools/auth_manager.py delete testuser
```

---

## 7. 版本记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0.0 | 2026-05-09 | 登录功能 + 账号管理 |
| 1.1.0 | 2026-05-10 | 个人中心基础框架 |
| 1.2.0 | 2026-05-10 | 日志功能日志展示/编辑分离 |
| 1.3.0 | 2026-05-10 | 暖色背景 |
| 1.4.0 | 2026-05-10 | 今日事项 JSON + 完成状态 |
| 1.5.0 | 2026-05-10 | Bug 修复 + 默认展示今天 |
