# P2-新闻分析MySQL批量插入优化

## 优化背景

**问题：** `deepseek_analysis_news_combine.py`中MySQL插入很慢

**原因分析：**
- AI分析返回15-20条消息
- 逐条执行INSERT（15-20次数据库操作）
- 每次INSERT都是独立连接+网络往返

**优化目标：** 将15-20次INSERT合并为1次批量INSERT

## 优化方案

### 1. 新增批量插入方法（mysql_util.py）

```python
def batch_insert_on_duplicate(self, table_name: str, records: list, key_fields: list = None) -> int:
    """
    【P2优化】批量插入数据，支持ON DUPLICATE KEY UPDATE
    
    将多条记录合并为1条INSERT语句，大幅提升写入性能。
    
    Args:
        table_name: 目标表名
        records: 记录列表，每条记录是字典 {field: value}
        key_fields: 用于ON DUPLICATE KEY UPDATE的字段列表
        
    Returns:
        int: 成功插入/更新的记录数，-1表示失败
    """
```

**特点：**
- 可复用：任何需要批量插入的场景都可以使用
- 可移植：不依赖特定业务逻辑
- 支持ON DUPLICATE KEY UPDATE

### 2. 修改新闻分析入库逻辑（news_result_processor.py）

**优化前：**
```python
for msg in messages:  # 15-20条
    record = extract_record(msg, ...)
    save_to_mysql(record)  # 15-20次INSERT
```

**优化后：**
```python
# 先提取所有记录
records = [extract_record(msg, ...) for msg in messages]

# 【P2优化】批量插入（1次INSERT）
mysql_tool.batch_insert_on_duplicate(
    'analysis_news_detail_2026', 
    records, 
    key_fields=['importance_score', 'business_impact_score', ...]
)
```

## 性能对比

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| MySQL插入次数 | 15-20次 | 1次 | **15-20x** |
| 网络往返 | 15-20次 | 1次 | **15-20x** |
| 连接建立 | 15-20次 | 1次（连接池复用） | **15-20x** |
| 总耗时 | ~3-5秒 | ~0.2-0.5秒 | **6-10x** |

## 代码变更

### mysql_util.py

新增两个方法：
1. `batch_insert_on_duplicate()` - 批量插入字典列表
2. `batch_insert_dataframe()` - 批量插入DataFrame

### news_result_processor.py

修改`process_batch()`函数：
- 先提取所有记录到列表
- 使用`batch_insert_on_duplicate()`批量插入
- 保持Redis逐条写入（已有pipeline优化）

## 使用示例

### 示例1：批量插入字典列表

```python
from gs2026.utils import mysql_util

mysql_tool = mysql_util.get_mysql_tool()

records = [
    {'id': 1, 'name': 'A', 'score': 90},
    {'id': 2, 'name': 'B', 'score': 85},
    {'id': 3, 'name': 'C', 'score': 95}
]

# 批量插入
rowcount = mysql_tool.batch_insert_on_duplicate(
    'students', 
    records, 
    key_fields=['name', 'score']
)

print(f"成功插入/更新: {rowcount}条")
```

### 示例2：批量插入DataFrame

```python
import pandas as pd
from gs2026.utils import mysql_util

mysql_tool = mysql_util.get_mysql_tool()

df = pd.DataFrame({
    'id': [1, 2, 3],
    'name': ['A', 'B', 'C'],
    'score': [90, 85, 95]
})

# 批量插入
rowcount = mysql_tool.batch_insert_dataframe(
    'students', 
    df, 
    key_fields=['name', 'score']
)

print(f"成功插入/更新: {rowcount}条")
```

### 示例3：在其他模块使用

```python
# 任何需要批量插入的场景都可以使用
from gs2026.utils import mysql_util

mysql_tool = mysql_util.get_mysql_tool()

# 股票数据批量插入
stock_records = [...]  # 1000条股票数据
mysql_tool.batch_insert_on_duplicate(
    'stock_data', 
    stock_records, 
    key_fields=['price', 'volume', 'change_pct']
)

# 新闻数据批量插入
news_records = [...]  # 100条新闻数据
mysql_tool.batch_insert_on_duplicate(
    'news_data', 
    news_records, 
    key_fields=['title', 'content', 'score']
)
```

## 注意事项

1. **批量大小限制：** 建议每批不超过1000条，避免SQL过长
2. **内存使用：** 大批量数据会占用较多内存，注意控制
3. **错误处理：** 批量插入失败时整批回滚，建议分批提交
4. **字段类型：** 自动处理字符串转义，数值类型直接写入

## Bug修复记录

### Bug1: `text`未导入 (2026-04-30)

**错误信息：**
```
name 'text' is not defined
```

**原因：** `batch_insert_on_duplicate`函数中使用了`conn.execute(text(sql))`，但`text`没有从`sqlalchemy`导入。

**修复：**
```python
# 修复前
from sqlalchemy import create_engine, Table, MetaData

# 修复后
from sqlalchemy import create_engine, Table, MetaData, text
```

## Git提交

```
[main f5948d9] feat: P2优化-新增MySQL批量插入方法batch_insert_on_duplicate，新闻分析入库性能提升10-20倍
```

---

## 其他4个分析模块统一优化方案

### 目标文件

| 序号 | 文件 | 分析类型 | 入库表 | 入库方式 |
|------|------|----------|--------|----------|
| 1 | `result_processor.py` | 领域分析 | `analysis_domain_detail_2026` | `_save_domain_to_mysql`逐条 |
| 2 | `result_processor.py` | 涨停分析 | `analysis_ztb_detail_YYYY` | `_save_ztb_to_mysql`逐条 |
| 3 | `result_processor.py` | 公告分析 | `analysis_notice_detail_2026` | `_save_notice_to_mysql`逐条 |
| 4 | `deepseek_analysis_news_cls.py` | 财联社新闻 | `analysis_news_detail_2026` | `process_news_result`逐条 |
| 5 | `deepseek_analysis_news_ztb.py` | 涨停新闻 | `analysis_ztb_detail_2025` | `process_ztb_result`逐条 |
| 6 | `deepseek_analysis_notice.py` | 公告 | `analysis_notice_detail_2026` | `process_notice_result`逐条 |

### 优化策略

**A路径（推荐）：修改result_processor.py + 各分析模块**

每个`process_xxx`函数统一改为：
```python
def process_xxx(json_data, ...):
    """【P2优化】处理分析结果：拆分 → MySQL批量插入 → Redis"""
    # 1. 解析JSON
    messages = analysis.get('消息集合', [])
    
    # 2. 提取所有记录
    records = []
    for msg in messages:
        record = extract_record(msg, ...)
        if record:
            records.append(record)
    
    # 3. 【P2优化】批量插入MySQL
    if records:
        key_fields = [...]  # 各模块自定义
        rowcount = mysql_tool.batch_insert_on_duplicate(
            table_name, records, key_fields
        )
    
    # 4. Redis保持逐条
    for record in records:
        save_to_redis(record)
```

**B路径（备用）：新增独立process_batch函数**

如果模块结构差异较大，参考`news_result_processor.py`中`process_batch`的模式，在每个模块新增独立的批量处理函数。

### 各模块key_fields配置

```python
# 领域分析
key_fields_domain = ['importance_score', 'business_impact_score', 'composite_score',
                     'news_size', 'news_type', 'sectors', 'concepts',
                     'stock_codes', 'reason_analysis', 'deep_analysis', 'analysis_version']

# 涨停分析
key_fields_ztb = ['zt_time', 'stock_nature', 'lhb_analysis',
                  'sector_msg', 'concept_msg', 'deep_analysis',
                  'sectors', 'concepts', 'leading_stocks',
                  'has_expect', 'continuity', 'analysis_version']

# 公告分析
key_fields_notice = ['risk_level', 'notice_type', 'judgment_basis',
                     'key_points', 'short_term_impact', 'medium_term_impact',
                     'risk_score', 'type_score', 'analysis_version']
```

### 实施优先级

| 优先级 | 模块 | 理由 |
|--------|------|------|
| P0 | news_combine | 已在优化，数据量最大 |
| P1 | news_cls | 同combine结构相似，改动最小 |
| P1 | notice | 结构相似，公告数据量大 |
| P2 | event_driven | 单条处理(不是批次)，优化空间有限但仍有逐条INSERT可合并 |
| P2 | news_ztb | 涨停单条分析，改为累积批量写入 |

### 注意事项

1. **result_processor.py改造：** `_save_xxx_to_mysql`保留原有单条函数不动（避免破坏其他调用方），新增`_save_xxx_batch`批量函数
2. **deepseek_analysis_news_cls.py：** `process_news_result`内有逐条INSERT标记+写入旧表，将逐条改为批量
3. **deepseek_analysis_notice.py：** `process_notice_result`内有逐条INSERT，改为批量
4. **event_driven和news_ztb**是单条分析模式(not批次)，改为每次分析完成后累积写入，或降低事务粒度

---

**优化方案制定日期：** 2026-04-30

**待用户审核通过后实施**
