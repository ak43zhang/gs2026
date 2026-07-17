# GS2026 工具使用手册

本文档汇总 GS2026 项目中所有独立工具程序的使用说明。

---

## 工具清单

| 工具名称 | 文件路径 | 功能说明 | 最后更新 |
|---------|---------|---------|---------|
| Redis 孤立缓存清理 | `tools/cleanup_redis_orphan.py` | 清理 Redis 中 MySQL 不存在的孤立新闻缓存 | 2026-04-13 |

---

## 目录结构

```
gs2026/
├── tools/                    # 工具程序目录
│   └── cleanup_redis_orphan.py
├── docs/
│   └── tools/               # 工具文档目录
│       └── README.md        # 本文档
└── configs/
    └── settings.yaml        # 工具共享配置文件
```

---

## 通用说明

### 环境要求

- Python 3.8+
- 项目虚拟环境已激活 (`.venv`)
- 配置文件 `configs/settings.yaml` 存在且配置正确

### 运行方式

所有工具均支持两种方式运行：

1. **直接运行** (推荐)
   ```bash
   cd F:\pyworkspace2026\gs2026
   python tools/xxx.py
   ```

2. **作为模块导入**
   ```python
   from tools.xxx import main
   main()
   ```

### 配置依赖

工具自动读取 `configs/settings.yaml` 中的配置：

```yaml
common:
  url: "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
  redis:
    host: 'localhost'
    port: 6379
```

---

## 工具详情

### cleanup_redis_orphan.py - Redis 孤立缓存清理工具

#### 功能说明

扫描 Redis 中的新闻缓存，删除 MySQL 中已不存在的孤立数据，保持 Redis 和 MySQL 数据一致性。

#### 检查范围

- `news:detail:{hash}` - 新闻详情 Hash
- `news:timeline:{date}` - 时间线 Sorted Set
- `news:type:{date}:{type}` - 类型索引 Sorted Set
- `news:top:{date}` - 评分排行 Sorted Set

#### 使用方法

**直接运行：**
```bash
cd F:\pyworkspace2026\gs2026
python tools/cleanup_redis_orphan.py
```

**定时任务 (Linux crontab)：**
```bash
# 每天凌晨 3 点执行
0 3 * * * cd /path/to/gs2026 && python tools/cleanup_redis_orphan.py >> logs/cleanup.log 2>&1
```

**Windows 任务计划程序：**
1. 创建基本任务
2. 触发器：每天 03:00
3. 操作：启动程序 `python.exe`
4. 参数：`tools/cleanup_redis_orphan.py`
5. 起始于：`F:\pyworkspace2026\gs2026`

#### 输出示例

```
============================================================
开始清理 Redis 孤立缓存
============================================================
扫描 Redis 中的 news:detail:* keys...
Redis 中共有 98 条 detail 缓存
查询 MySQL 确认哪些 hash 存在...
MySQL 中存在 80 条
Redis 有但 MySQL 没有的数据: 18 条
开始删除 18 条孤立缓存...
成功删除 18 条孤立缓存
示例 (前5条): ['112f86b541...', '2bc35988de...', ...]
============================================================
清理完成
============================================================
```

#### 注意事项

1. **生产环境建议先备份 Redis**：
   ```bash
   redis-cli BGSAVE
   ```

2. **大批量清理时**可能影响 Redis 性能，建议在低峰期运行

3. **分批查询**：MySQL 查询采用 500 条分批，避免 SQL 过长

---

## 新增工具规范

开发新工具时，请遵循以下规范：

### 1. 文件位置
- 工具程序放在 `tools/` 目录
- 使用说明更新本文档

### 2. 文件头模板
```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""工具名称 - 简短描述

功能说明:
    详细功能描述

使用方法:
    python tools/xxx.py [参数]

依赖配置:
    - common.url        - MySQL 连接 URL
    - common.redis.host - Redis 主机

作者: GS2026
版本: 1.0.0
日期: YYYY-MM-DD
"""
```

### 3. 路径处理
```python
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))
```

### 4. 配置读取
```python
from gs2026.utils import config_util, log_util

url = config_util.get_config('common.url')
redis_host = config_util.get_config('common.redis.host', 'localhost')
```

### 5. 日志记录
```python
logger = log_util.setup_logger('tool_name')
logger.info("操作信息")
logger.error("错误信息")
```

---

## 更新记录

| 日期 | 版本 | 更新内容 |
|-----|------|---------|
| 2026-04-13 | 1.0.0 | 初始版本，添加 cleanup_redis_orphan.py |

---

*文档维护：GS2026 开发团队*
