# MysqlTool 单例优化文档

**优化日期**: 2026-04-17  
**优化目标**: 消除 `combine_collection.py` 启动时 MysqlTool 重复初始化日志  
**影响范围**: 24个模块的 MysqlTool 实例化方式

---

## 一、问题分析

### 1.1 现象

`combine_collection.py` 启动时，日志中出现大量重复的 MysqlTool 初始化日志：

```
[gs2026.utils.mysql_util] 调用 MysqlTool | 参数: mysql+pymysql://root:123456@...
[gs2026.utils.mysql_util] MysqlTool 完成 | 耗时: 0.001s
```

重复出现 24 次。

### 1.2 根因

1. **24个模块**在模块级别直接调用 `mysql_util.MysqlTool(url)` 创建实例
2. `MysqlTool` 类使用了 `@log_decorator` 装饰器，每次实例化都触发日志
3. 虽然 `MysqlTool` 有单例模式（`__new__` 保证只有一个实例），但装饰器在 `__new__` 外层，导致每次调用都打日志

### 1.3 受影响模块

| 序号 | 模块路径 | 原写法 |
|------|----------|--------|
| 1 | `collection/base/zt_collection.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 2 | `collection/base/base_collection.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 3 | `collection/base/baostock_collection.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 4 | `collection/base/bk_gn_collection.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 5 | `collection/base/wencai_collection.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 6 | `collection/base/stock_daily_collection.py` | `self.mysql_tool = mysql_util.MysqlTool(self.url)` |
| 7 | `collection/other/bond_zh_cov.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 8 | `collection/other/akshare_collection.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 9 | `collection/other/concept_collection.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 10 | `collection/other/ods.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 11 | `collection/other/stock_update_collection.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 12 | `collection/risk/akshare_risk_history.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 13 | `collection/risk/notice_risk_history.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 14 | `collection/risk/wencai_risk_history.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 15 | `collection/risk/wencai_risk_year_history.py` | `mysql_tool = mysql_util.MysqlTool(url)` |
| 16 | `analysis/deepseek/result_processor.py` | `mysql_tool = mu.MysqlTool(url)` |
| 17 | `analysis/deepseek/news_result_processor.py` | `mysql_tool = mu.MysqlTool(url)` |
| 18 | `analysis/deepseek/combine_ztb_area.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 19 | `analysis/deepseek/deepseek_analysis_event_driven.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 20 | `analysis/deepseek/deepseek_analysis_news_cls.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 21 | `analysis/deepseek/deepseek_analysis_news_combine.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 22 | `analysis/deepseek/deepseek_analysis_news_ztb.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 23 | `analysis/deepseek/deepseek_analysis_notice.py` | `mysql_util = mysql_util.MysqlTool(url)` ⚠️ 变量名冲突 |
| 24 | `analysis/deepseek/migrate_analysis_news.py` | `mysql_tool = mu.MysqlTool(url)` |

> ⚠️ 标记的模块使用 `mysql_util` 作为变量名，覆盖了模块引用，需要特殊处理

---

## 二、优化方案

### 2.1 核心改动

#### A. 修改 `mysql_util.py`

1. **移除 `MysqlTool` 类上的 `@log_decorator`** - 消除每次实例化的日志
2. **优化 `get_mysql_tool()` 工厂函数** - 只在首次创建时输出日志

```python
# 移除 @log_decorator
class MysqlTool:
    _instance = None
    _lock = threading.Lock()
    ...

# 优化工厂函数
_mysql_tool_instance = None

def get_mysql_tool(url=None) -> MysqlTool:
    """获取全局唯一 MysqlTool 实例"""
    global _mysql_tool_instance
    if _mysql_tool_instance is None:
        _mysql_tool_instance = MysqlTool(url)
        logger.info(f"MysqlTool 全局单例创建完成")
    return _mysql_tool_instance
```

#### B. 批量替换所有模块

**普通模块**（变量名为 `mysql_tool`）：
```python
# 修改前
mysql_tool = mysql_util.MysqlTool(url)

# 修改后
mysql_tool = mysql_util.get_mysql_tool(url)
```

**变量名冲突模块**（变量名为 `mysql_util`，覆盖了模块引用）：
```python
# 修改前
from gs2026.utils import mysql_util
mysql_util = mysql_util.MysqlTool(url)

# 修改后
from gs2026.utils import mysql_util
mysql_tool = mysql_util.get_mysql_tool(url)
# 并修改后续所有 mysql_util.xxx 引用为 mysql_tool.xxx
```

**使用别名的模块**（`import mysql_util as mu`）：
```python
# 修改前
mysql_tool = mu.MysqlTool(url)

# 修改后
mysql_tool = mu.get_mysql_tool(url)
```

### 2.2 不影响其他项目

- `MysqlTool` 类本身不变（单例、连接池、所有方法）
- `get_mysql_tool()` 是已有函数，只是优化日志
- 各模块独立运行时效果相同（单例保证只有一个实例）

---

## 三、优化效果

### 优化前（启动时日志）
```
[mysql_util] 调用 MysqlTool × 24次
[mysql_util] MysqlTool 完成 × 24次
共 48 行日志
```

### 优化后（启动时日志）
```
MysqlTool 全局单例创建完成 × 1次
共 1 行日志
```

---

## 四、回滚方案

回滚到优化前的提交：
```bash
git revert <优化提交hash>
```

或使用备份分支：
```bash
git checkout pre-mysql-optimization -- .
```

---

## 五、相关文件

- **核心工具**: `src/gs2026/utils/mysql_util.py`
- **入口程序**: `src/gs2026/analysis/worker/message/deepseek/combine_collection.py`
- **本文档**: `docs/05-性能优化/MysqlTool单例优化.md`
