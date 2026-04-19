# DeepSeek 敏感词拒绝应答优化方案

**文档版本**: v1.0  
**创建日期**: 2026-04-20  
**功能模块**: 新闻分析 - DeepSeek AI 分析  
**回退标签**: `pre-sensitive-word-optimization`  
**相关文件**: 
- `src/gs2026/analysis/worker/message/deepseek/deepseek_analysis_news_cls.py`
- `src/gs2026/analysis/worker/message/deepseek/deepseek_analysis_news_combine.py`

---

## 一、问题背景

### 现象
DeepSeek 在执行批量新闻分析时，某些消息内容触发平台敏感词/禁忌词过滤，返回拒绝回答：
> "你好，这个问题我暂时无法回答，让我们换个话题再聊聊吧。"

### 影响
| 影响 | 说明 |
|------|------|
| 批次全废 | 一条敏感消息导致整批 15-18 条消息分析失败 |
| 无限循环 | 敏感消息 `analysis=NULL`，每次轮询都被选中 |
| 资源浪费 | DeepSeek 账号额度被无效消耗 |
| 正常消息被连带 | 同批次无敏感内容的消息也无法得到分析结果 |

---

## 二、设计方案

### 核心策略：三层防护

```
第1层：拒绝检测 — 识别 DeepSeek 拒绝回答的固定话术
第2层：逐条重试 — 批次失败后逐条发送，隔离问题消息
第3层：失败计数 — 记录失败次数，超过阈值永久跳过
```

### 2.1 拒绝检测

已知的拒绝回答模式（可扩展）：

```python
REFUSAL_PATTERNS = [
    '我暂时无法回答',
    '让我们换个话题',
    '我无法处理',
    '无法为您提供',
    '我不能回答',
    '违反了我的使用政策',
    '不适合讨论',
    '无法协助',
    '抱歉，我不能',
]
```

### 2.2 失败计数机制

利用现有 `analysis` 字段（VARCHAR），无需修改表结构：

| analysis 值 | 含义 | 行为 |
|-------------|------|------|
| `NULL` 或 `''` | 未分析 | 正常选中处理 |
| `'1'` | 分析成功 | 不再处理 |
| `'fail_1'` | 失败1次 | 继续重试 |
| `'fail_2'` | 失败2次 | 继续重试 |
| `'fail_3'` | 失败3次 | 达到阈值 |
| `'skip'` | 永久跳过 | 永不处理 |

### 2.3 查询 SQL 调整

```sql
-- 原 SQL
SELECT ... WHERE (analysis IS NULL OR analysis='') ORDER BY ...

-- 优化后：包含 fail_N 状态（可重试），排除 skip 和成功
SELECT ... WHERE (analysis IS NULL OR analysis='' OR analysis LIKE 'fail_%') ORDER BY ...
```

### 2.4 流程图

```
批量 Prompt (15-18条)
    │
    ▼
DeepSeek 返回结果
    │
    ├── 正常 JSON → 解析成功 → 写入数据库 ✅
    │       │
    │       └── 部分消息ID缺失 → 缺失的消息增加失败计数
    │
    ├── 拒绝回答 → 检测到拒绝模式
    │       │
    │       ▼
    │   逐条重试（每条单独发送 Prompt）
    │       │
    │       ├── 单条成功 → 写入数据库 ✅
    │       └── 单条失败/拒绝 → 增加失败计数
    │               │
    │               ├── 未达阈值 → analysis='fail_N' → 下次轮询继续重试
    │               └── 达到阈值(3次) → analysis='skip' → 永久跳过 ⛔
    │
    └── JSON 解析失败 → 同上（逐条重试）
```

---

## 三、实施步骤

### 3.1 修改 `deepseek_analysis_news_cls.py`

1. 添加拒绝检测常量和函数
2. 修改 `deepseek_ai` 函数：添加拒绝检测和逐条重试分支
3. 添加 `_retry_one_by_one` 逐条重试函数
4. 添加 `_increment_fail_count` 失败计数函数
5. 修改 `get_news_cls_analysis` 函数：调整查询 SQL

### 3.2 修改 `deepseek_analysis_news_combine.py`

同 3.1，保持两个文件逻辑一致。

---

## 四、兼容性

| 方面 | 处理 |
|------|------|
| 数据库无需改表 | 利用现有 `analysis` VARCHAR 字段 |
| 查询兼容 | `fail_N` 状态仍被选中重试，`skip` 永久排除 |
| 其他模块 | 不影响，仅修改新闻分析模块 |
| 历史数据 | 不影响，`NULL` 和 `''` 仍被正常处理 |
| 回滚方案 | `git checkout pre-sensitive-word-optimization` |

## 五、回滚

```bash
# 代码回退
git checkout pre-sensitive-word-optimization

# 数据回退（将 skip/fail_N 状态还原）
UPDATE news_cls2026 SET analysis=NULL WHERE analysis LIKE 'fail_%' OR analysis='skip';
UPDATE news_combine2026 SET analysis=NULL WHERE analysis LIKE 'fail_%' OR analysis='skip';
```

---

## 六、验证

- **测试数据**: `内容hash = 2eddd7fc394cb4f1ecf470a47ae0467d`
- **验证方式**: 使用该 ID 单条分析，观察拒绝检测和失败计数是否正常工作

---

*文档创建时间: 2026-04-20 00:01*
