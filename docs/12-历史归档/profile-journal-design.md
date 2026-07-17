# GS2026 个人中心 & 日志功能设计文档

> 版本: 1.0.0
> 日期: 2026-05-10
> 状态: 待审核

---

## 1. 功能概述

在导航栏退出按钮左侧新增一个「个人中心」图标按钮，点击后进入个人中心页面。个人中心作为可扩展的功能入口，首期实现「日志」功能模块。

### 1.1 日志功能

以日期为维度的个人工作日志系统，每天可记录：
- 日志内容（工作日志/心得体会）
- 今日事项（待办/已完成事项）
- 备注（补充信息）
- 标签（自定义分类标签）
- 心情/状态（可选）

---

## 2. 前端设计

### 2.1 导航栏改动

在退出按钮左侧新增个人中心图标：

```
[首页] [数据监控] [数据采集] ... [智能选股]          [👤] [退出]
                                                     ↑
                                              个人中心图标
```

- 图标使用 SVG 用户头像图标（或 emoji 👤）
- 点击跳转到 `/profile`
- 样式与导航栏其他按钮一致

### 2.2 个人中心页面 `/profile`

左侧菜单 + 右侧内容区的布局：

```
┌─────────────────────────────────────────────────┐
│  [导航栏]                                        │
├──────────┬──────────────────────────────────────┤
│  功能菜单  │  内容区                              │
│           │                                      │
│  📝 日志  │  [日志内容]                           │
│  📊 统计  │                                      │
│  ⚙️ 设置  │                                      │
│  (预留)   │                                      │
│           │                                      │
└──────────┴──────────────────────────────────────┘
```

首期只实现「日志」菜单项，其他菜单项预留位置。

### 2.3 日志页面

#### 2.3.1 日历视图

顶部显示月份切换器 + 日历网格：
- 有日志的日期高亮显示
- 点击日期进入该日的日志编辑/查看

#### 2.3.2 日志编辑/查看

选中某一天后，右侧展示该日的日志表单：

| 字段 | 类型 | 说明 |
|------|------|------|
| 日期 | 日期选择器 | 当前选中日期（可切换） |
| 日志内容 | 多行文本 | 工作日志、心得体会 |
| 今日事项 | 多行文本 | 待办/已完成事项 |
| 备注 | 多行文本 | 补充信息 |
| 标签 | 标签输入 | 自定义标签（如：开发、会议、学习） |
| 心情 | 单选 | 😊 😐 😫 🔥（可选） |

- 自动保存（失焦或 Ctrl+S 触发）
- 支持新增和编辑（同一天只有一条记录，重复写入为更新）

---

## 3. 数据库设计

### 3.1 新建表：`user_journals`

```sql
CREATE TABLE user_journals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL COMMENT '用户名（关联 accounts.username）',
    journal_date DATE NOT NULL COMMENT '日志日期',
    content TEXT COMMENT '日志内容/心得',
    todo_items TEXT COMMENT '今日事项',
    remarks TEXT COMMENT '备注',
    tags VARCHAR(500) COMMENT '标签（逗号分隔）',
    mood VARCHAR(20) COMMENT '心情状态',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_date (username, journal_date),
    KEY idx_username (username),
    KEY idx_journal_date (journal_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户工作日志';
```

### 3.2 设计说明

- 每个用户每天最多一条记录（`UNIQUE KEY uk_user_date`）
- 写入时使用 `INSERT ... ON DUPLICATE KEY UPDATE` 实现新增/更新合一
- `tags` 字段用逗号分隔存储，简单高效
- `mood` 字段存储 emoji 或预定义值

---

## 4. 后端实现

### 4.1 新增文件

- `src/gs2026/dashboard2/routes/profile.py` — 个人中心路由蓝图

### 4.2 路由定义

| 路由 | 方法 | 说明 |
|------|------|------|
| `/profile` | GET | 个人中心页面 |
| `/api/journal/get` | GET | 获取指定日期的日志 |
| `/api/journal/save` | POST | 保存/更新日志 |
| `/api/journal/list` | GET | 获取指定月份有日志的日期列表 |
| `/api/journal/delete` | POST | 删除指定日期的日志 |

### 4.3 API 详情

#### GET `/api/journal/get?date=2026-05-10`

```json
{
    "success": true,
    "data": {
        "journal_date": "2026-05-10",
        "content": "今天完成了登录功能...",
        "todo_items": "1. 完成日志功能\n2. 代码审查",
        "remarks": "明天需要部署",
        "tags": "开发,功能",
        "mood": "🔥"
    }
}
```

#### POST `/api/journal/save`

请求体：
```json
{
    "date": "2026-05-10",
    "content": "...",
    "todo_items": "...",
    "remarks": "...",
    "tags": "开发,功能",
    "mood": "😊"
}
```

响应：
```json
{"success": true, "message": "保存成功"}
```

#### GET `/api/journal/list?year=2026&month=5`

```json
{
    "success": true,
    "data": ["2026-05-01", "2026-05-03", "2026-05-10"]
}
```

#### POST `/api/journal/delete`

```json
{"date": "2026-05-10"}
```

---

## 5. 前端文件

### 5.1 新增文件

- `src/gs2026/dashboard2/templates/profile.html` — 个人中心页面（含日志功能）

### 5.2 页面结构

单页面实现，使用 JavaScript 动态切换内容：
- 左侧菜单切换功能模块
- 日历组件使用纯 JS 实现（无额外依赖）
- 日志编辑使用 textarea + 自动保存
- AJAX 调用后端 API

### 5.3 样式

- 复用现有深色主题配色
- 日历网格：深色背景 + 高亮有日志的日期
- 表单：与登录页一致的输入框样式
- 响应式布局

---

## 6. 配置

无需额外配置。个人中心功能跟随登录功能：
- `auth.enabled: true` → 个人中心可用（需登录）
- `auth.enabled: false` → 个人中心入口隐藏

---

## 7. 影响范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/gs2026/dashboard2/routes/profile.py` | 新增 | 个人中心路由 |
| `src/gs2026/dashboard2/templates/profile.html` | 新增 | 个人中心页面 |
| `src/gs2026/dashboard2/app.py` | 修改 | 注册 profile 蓝图 |
| `src/gs2026/dashboard2/templates/*.html`（13个） | 修改 | 导航栏添加个人中心图标 |
| `src/gs2026/dashboard2/static/css/pages.css` | 修改 | 个人中心图标样式 |
| MySQL | DDL | 新建 `user_journals` 表 |

---

## 8. 扩展性

个人中心预留以下扩展位：
- **统计面板**：日志写入频率、标签统计
- **设置**：修改密码、个人偏好
- **收藏夹**：收藏的股票/新闻
- **通知中心**：系统消息

后续新增功能只需：
1. 在左侧菜单添加入口
2. 新增对应的内容区 HTML + API

---

## 9. 安全性

- 所有 API 需要登录（`before_request` 已拦截）
- 日志数据按 `username` 隔离，用户只能访问自己的日志
- API 从 `session['username']` 获取当前用户，不接受前端传入用户名

---

## 10. 依赖

无新增 Python 包。使用：
- Flask session（已有）
- SQLAlchemy（已有）
- 前端纯 JS（无新增库）
