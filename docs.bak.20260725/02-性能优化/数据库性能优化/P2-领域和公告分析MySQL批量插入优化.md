# P2优化 - AI分析模块MySQL批量插入

## 修改日期
2026-04-30

## 修改背景

AI分析模块（领域分析、公告分析）在将DeepSeek返回的JSON拆分入库时，采用逐条INSERT方式写入MySQL，每条记录一次网络往返，性能低下。

## 问题分析

### 领域分析（event_driven）
```
DeepSeek返回 ~30条消息JSON
    └─ result_processor.process_domain()
        └─ for msg in messages:  ← 30次循环
            └─ _save_domain_to_mysql(record)  ← 30次独立INSERT
```
**瓶颈：** 30次数据库往返

### 公告分析（notice）
```
DeepSeek返回 5-15条公告JSON
    └─ result_processor.process_notice()
        └─ for notice in notices:  ← 5-15次循环
            └─ _save_notice_to_mysql(record)  ← 5-15次独立INSERT
```
**瓶颈：** 5-15次数据库往返

## 优化方案

将逐条INSERT改为`batch_insert_on_duplicate()`批量插入（已在`mysql_util.py`中实现）。

### 优化后流程
```
process_domain() / process_notice()
    ├─ 提取所有记录到列表
    ├─ mysql_tool.batch_insert_on_duplicate()  ← 1次批量INSERT
    └─ Redis逐条写入（保持不变）
```

## 修改文件

### `src/gs2026/analysis/worker/message/deepseek/result_processor.py`

#### process_domain() 修改
```python
def process_domain(json_data, main_area, child_area, event_date, version='1.0.0'):
    """【P2优化】处理领域分析结果：拆分 → MySQL批量插入 → Redis"""
    # 1. 提取所有记录
    records = []
    for msg in messages:
        record = _extract_domain_record(msg, main_area, child_area, version)
        if record:
            records.append(record)
    
    # 2. 【P2优化】批量插入MySQL（1次INSERT代替~30次）
    key_fields = ['importance_score', 'business_impact_score', 'composite_score',
                  'news_size', 'news_type', 'sectors', 'concepts',
                  'stock_codes', 'reason_analysis', 'deep_analysis', 'analysis_version']
    rowcount = mysql_tool.batch_insert_on_duplicate(
        'analysis_domain_detail_2026', records, key_fields)
    
    # 3. Redis保持逐条
    for record in records:
        _save_domain_to_redis(record)
```

#### process_notice() 修改
```python
def process_notice(json_data, version='1.0.0'):
    """【P2优化】处理公告分析结果：拆分 → MySQL批量插入 → Redis"""
    # 1. 提取所有记录
    records = []
    for notice in notices:
        record = _extract_notice_record(notice, version)
        if record:
            records.append(record)
    
    # 2. 【P2优化】批量插入MySQL（1次INSERT代替5-15次）
    key_fields = ['risk_level', 'notice_type', 'notice_category',
                  'judgment_basis', 'key_points', 'short_term_impact',
                  'medium_term_impact', 'risk_score', 'type_score', 'analysis_version']
    rowcount = mysql_tool.batch_insert_on_duplicate(
        'analysis_notice_detail_2026', records, key_fields)
    
    # 3. Redis保持逐条
    for record in records:
        _save_notice_to_redis(record)
```

## 性能对比

| 模块 | 优化前 | 优化后 | 提升倍数 |
|------|--------|--------|----------|
| 领域分析 | ~30次INSERT | 1次批量INSERT | **30x** |
| 公告分析 | 5-15次INSERT | 1次批量INSERT | **5-15x** |

## 5个分析模块最终状态

| 模块 | 入库方式 | 状态 |
|------|----------|------|
| 综合新闻（combine） | `news_result_processor.process_batch()` | ✅ 已优化 |
| 财联社新闻（cls） | `news_result_processor.process_batch()` | ✅ 已优化 |
| 领域事件（event_driven） | `result_processor.process_domain()` | ✅ 本次优化 |
| 公告分析（notice） | `result_processor.process_notice()` | ✅ 本次优化 |
| 涨停分析（ztb） | `result_processor.process_ztb()` | ⏭️ 跳过（单条） |

## Git提交

```
[main 49e9325] feat: P2优化-领域分析和公告分析MySQL批量插入（process_domain 30x, process_notice 5-15x）
```

## 注意事项

1. `_save_domain_to_mysql()`、`_save_notice_to_mysql()` 原有单条函数保留不动（可能有其他调用方）
2. Redis写入保持逐条（已有pipeline优化，且Redis写入本身很快）
3. `batch_insert_on_duplicate()`已在`mysql_util.py`中实现，支持ON DUPLICATE KEY UPDATE
