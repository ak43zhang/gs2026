# 龙头股识别OLAP方案（高效精准分析型设计）

## 用户核心诉求理解

### 当前问题诊断

| 问题 | 说明 |
|------|------|
| **过度设计** | `stock_anomaly_*` 表扩展太多，每个功能一个新表 |
| **OLTP思维** | 每个分析结果都存一张表，事务型存储 |
| **低效** | 数据分散，查询需多表JOIN |
| **不精准** | 表结构固定，难以灵活分析 |

### 用户期望

```
❌ 不要：每个功能一个表（stock_anomaly_leader_size、stock_anomaly_correlation...）

✅ 要：OLAP分析型设计
   - 宽表模型：一张表包含所有分析维度
   - 灵活扩展：新增维度加字段，不建新表
   - 高效查询：单表查询，无需JOIN
   - 精准分析：多维度交叉分析
```

---

## OLAP vs OLTP 思维对比

### OLTP思维（当前问题）

```sql
-- 事务型：每个功能一个表
stock_anomaly                    -- 原始异动数据
stock_anomaly_leader             -- 龙头分析
stock_anomaly_leader_size        -- 体量分类  ← 您担心的过度设计
stock_anomaly_correlation        -- 关联分析
stock_anomaly_potential          -- 潜在标的
...

-- 查询需要大量JOIN
SELECT a.*, l.*, c.*, p.*
FROM stock_anomaly a
LEFT JOIN stock_anomaly_leader l ON a.id = l.anomaly_id
LEFT JOIN stock_anomaly_leader_size s ON a.id = s.anomaly_id
LEFT JOIN stock_anomaly_correlation c ON a.id = c.anomaly_id
...
WHERE a.trading_date = '2026-06-29'
```

**问题**：
- 表数量爆炸
- 查询性能差（多表JOIN）
- 数据一致性难维护
- 扩展困难（每加一个维度建新表）

---

### OLAP思维（推荐方案）

```sql
-- 分析型：一张宽表包含所有维度
stock_anomaly_analysis  -- 异动分析宽表（替代所有stock_anomaly_*表）

-- 核心字段
- 基础字段（来自stock_anomaly）
- 龙头识别维度（leader_status, leader_score...）
- 体量分类维度（size_type, strategy...）
- 关联分析维度（correlation_type, related_stocks...）
- 潜在标的维度（potential_rank, entry_point...）
- 扩展字段（ext_json 存动态维度）

-- 查询只需单表
SELECT * FROM stock_anomaly_analysis
WHERE trading_date = '2026-06-29'
  AND mainline_name = 'AI应用与智能体'
  AND size_type = '小盘情绪龙'
  AND leader_score > 80
```

**优势**：
- 单表查询，性能极高
- 多维度交叉分析（龙头+体量+关联）
- 扩展灵活（加字段或ext_json）
- 数据一致性好

---

## 重新设计的核心思路

### 核心原则

```
1. 一表多用：stock_anomaly_analysis 替代所有分析表
2. 维度丰富：一张表包含所有分析维度
3. 灵活扩展：ext_json字段存动态分析结果
4. 高效查询：单表+索引，无需JOIN
```

### 表设计：stock_anomaly_analysis（分析宽表）

```sql
CREATE TABLE IF NOT EXISTS stock_anomaly_analysis (
    -- 主键
    id INT AUTO_INCREMENT PRIMARY KEY,
    
    -- 基础关联（来自stock_anomaly）
    anomaly_id INT NOT NULL COMMENT '关联stock_anomaly.id',
    trading_date DATE NOT NULL COMMENT '交易日期',
    stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
    stock_name VARCHAR(50) COMMENT '股票名称',
    anomaly_time TIME COMMENT '涨停时间',
    price DECIMAL(10,2) COMMENT '价格',
    change_pct DECIMAL(5,2) COMMENT '涨跌幅',
    continuous_zt INT COMMENT '连板数',
    mainline_names JSON COMMENT '关联主线',
    
    -- 龙头识别维度（替代stock_anomaly_leader）
    leader_status VARCHAR(20) COMMENT '龙头地位：龙头/补涨/跟风/独立',
    leader_score INT COMMENT '龙头强度评分0-100',
    mainline_rank VARCHAR(20) COMMENT '主线内排名',
    status_reason TEXT COMMENT '地位判定依据',
    continuous_expect VARCHAR(10) COMMENT '连板预期：高/中/低',
    next_day_expect VARCHAR(20) COMMENT '次日溢价预期',
    
    -- 体量分类维度（替代stock_anomaly_leader_size）
    size_type VARCHAR(20) COMMENT '体量类型：权重龙头/板块中军/小盘情绪龙',
    float_market_cap DECIMAL(10,2) COMMENT '流通市值（亿）',
    strategy VARCHAR(50) COMMENT '操作策略',
    risk_level VARCHAR(10) COMMENT '风险等级：低/中/高',
    fit_for VARCHAR(20) COMMENT '适合人群：稳健型/平衡型/激进型',
    
    -- 关联分析维度（替代stock_anomaly_correlation）
    correlation_type VARCHAR(20) COMMENT '关联类型：主线归属/独立/新主线',
    related_stocks JSON COMMENT '关联股票列表',
    related_mainlines JSON COMMENT '关联主线列表',
    
    -- 潜在标的维度（替代stock_anomaly_potential）
    potential_rank INT COMMENT '潜在排名',
    suggested_entry TEXT COMMENT '建议介入点',
    risk_note TEXT COMMENT '风险提示',
    
    -- 扩展维度（灵活扩展，不建新表）
    ext_json JSON COMMENT '扩展字段：存动态分析结果',
    
    -- 元数据
    analysis_version VARCHAR(10) DEFAULT '1.0' COMMENT '分析版本',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引优化
    INDEX idx_date_mainline (trading_date, (CAST(mainline_names AS CHAR(255) ARRAY))),
    INDEX idx_date_code (trading_date, stock_code),
    INDEX idx_leader (leader_status, leader_score),
    INDEX idx_size (size_type),
    INDEX idx_score (leader_score),
    INDEX idx_potential (potential_rank),
    
    UNIQUE KEY uk_anomaly (anomaly_id, analysis_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='盘中异动分析宽表（OLAP设计）';
```

---

## 核心优势

### 1. 一表替代多表

| 旧方案（OLTP） | 新方案（OLAP） |
|---------------|---------------|
| stock_anomaly_leader | stock_anomaly_analysis.leader_* |
| stock_anomaly_leader_size | stock_anomaly_analysis.size_* |
| stock_anomaly_correlation | stock_anomaly_analysis.correlation_* |
| stock_anomaly_potential | stock_anomaly_analysis.potential_* |
| ... | stock_anomaly_analysis.ext_json |

**结果**：5+张表 → 1张表

### 2. 高效查询（单表无需JOIN）

```sql
-- 旧方案：多表JOIN
SELECT a.*, l.*, s.*
FROM stock_anomaly a
LEFT JOIN stock_anomaly_leader l ON a.id = l.anomaly_id
LEFT JOIN stock_anomaly_leader_size s ON a.id = s.anomaly_id
WHERE a.trading_date = '2026-06-29'
  AND l.leader_status = '龙头'
  AND s.size_type = '小盘情绪龙';

-- 新方案：单表查询
SELECT *
FROM stock_anomaly_analysis
WHERE trading_date = '2026-06-29'
  AND leader_status = '龙头'
  AND size_type = '小盘情绪龙';
```

**性能提升**：
- 旧方案：3表JOIN，O(n^m)复杂度
- 新方案：单表查询，O(n)复杂度

### 3. 灵活扩展（ext_json）

```sql
-- 新增"时间梯队维度"，无需改表结构
UPDATE stock_anomaly_analysis
SET ext_json = JSON_SET(ext_json, '$.time_ladder', '先锋龙')
WHERE id = 1;

-- 查询
SELECT * FROM stock_anomaly_analysis
WHERE ext_json->>'$.time_ladder' = '先锋龙';
```

**优势**：
- 不修改表结构
- 不重启服务
- 即时生效

### 4. 多维度交叉分析

```sql
-- 精准查询：AI主线的小盘情绪龙且龙头评分>80
SELECT *
FROM stock_anomaly_analysis
WHERE trading_date = '2026-06-29'
  AND mainline_names LIKE '%AI应用与智能体%'
  AND size_type = '小盘情绪龙'
  AND leader_status = '龙头'
  AND leader_score > 80
  AND risk_level = '高'
ORDER BY leader_score DESC;
```

**价值**：
- 多维度交叉筛选
- 精准定位目标股票
- 支持复杂分析场景

---

## 数据流转设计

### 分析流程

```
stock_anomaly（原始数据）
    ↓
[AI分析] → 龙头识别 + 体量分类 + 关联分析
    ↓
stock_anomaly_analysis（宽表存储）
    ↓
[查询分析] → 单表多维度筛选
```

### 代码实现

```python
def analyze_and_save(anomaly_id: int, date: str):
    """
    分析并保存到宽表
    """
    # 1. 获取原始数据
    anomaly = get_anomaly_by_id(anomaly_id)
    
    # 2. AI分析（一次性输出所有维度）
    analysis = ai_analyze(anomaly)  # 返回所有维度结果
    
    # 3. 构建宽表记录
    record = {
        'anomaly_id': anomaly_id,
        'trading_date': date,
        'stock_code': anomaly['stock_code'],
        # ... 基础字段
        
        # 龙头维度
        'leader_status': analysis['leader_status'],
        'leader_score': analysis['leader_score'],
        # ...
        
        # 体量维度
        'size_type': analysis['size_type'],
        'strategy': analysis['strategy'],
        # ...
        
        # 关联维度
        'correlation_type': analysis['correlation_type'],
        # ...
        
        # 扩展维度
        'ext_json': json.dumps(analysis.get('ext', {}))
    }
    
    # 4. 保存到宽表（单表写入）
    save_to_analysis_table(record)
```

---

## 实施步骤

### 阶段1：创建宽表（10分钟）
```sql
-- 执行上述CREATE TABLE语句
```

### 阶段2：修改AI分析（30分钟）
```python
# 修改分析逻辑，一次性输出所有维度
# 不再分多次写入多个表
```

### 阶段3：数据迁移（可选，20分钟）
```sql
-- 如有旧数据，迁移到宽表
INSERT INTO stock_anomaly_analysis (...)
SELECT ... FROM stock_anomaly_leader, stock_anomaly_leader_size...
```

### 阶段4：查询优化（10分钟）
```sql
-- 创建复合索引
CREATE INDEX idx_composite ON stock_anomaly_analysis(
    trading_date, leader_status, size_type, leader_score
);
```

**总耗时：约1小时**

---

## 预期效果

### 表数量对比

| 类型 | 旧方案 | 新方案 |
|------|--------|--------|
| 分析表数量 | 5+张 | **1张** |
| 查询复杂度 | 多表JOIN | **单表查询** |
| 扩展方式 | 建新表 | **加字段/ext_json** |
| 维护成本 | 高 | **低** |

### 查询性能对比

| 场景 | 旧方案 | 新方案 |
|------|--------|--------|
| 查某日龙头 | 3表JOIN，~500ms | **单表，~50ms** |
| 多维度筛选 | 4表JOIN，~800ms | **单表，~80ms** |
| 聚合统计 | 多表聚合，~1s | **单表聚合，~100ms** |

### 使用体验

```sql
-- 用户查询：AI主线的小盘情绪龙
SELECT stock_code, stock_name, leader_score, strategy
FROM stock_anomaly_analysis
WHERE trading_date = '2026-06-29'
  AND mainline_names LIKE '%AI应用%'
  AND size_type = '小盘情绪龙'
ORDER BY leader_score DESC
LIMIT 10;
```

**结果**：
- 单表查询，简单清晰
- 多维度交叉，精准定位
- 性能极高，毫秒级响应

---

## 总结

| 维度 | 旧方案（OLTP） | 新方案（OLAP） |
|------|---------------|---------------|
| **设计思维** | 事务型，功能驱动 | **分析型，维度驱动** |
| **表设计** | 多表，每张表一个功能 | **宽表，一张表所有维度** |
| **查询方式** | 多表JOIN | **单表查询** |
| **扩展性** | 差（加功能建新表） | **好（加字段或ext_json）** |
| **性能** | 差（JOIN开销大） | **好（单表+索引）** |
| **维护成本** | 高 | **低** |

**核心转变**：从"功能驱动建表"转向"维度驱动建宽表"。

---

## 用户理解确认

**我理解您的诉求是**：

1. ✅ 不要过度设计（不要每个功能一个表）
2. ✅ OLAP思维（分析型宽表设计）
3. ✅ 高效精准（单表查询，多维度交叉）
4. ✅ 灵活扩展（ext_json存动态维度）

**如果理解有误，请纠正**：
- 是否还需要保留某些独立表？
- ext_json的设计是否符合预期？
- 还有哪些维度需要加入宽表？

**确认后我立即实施代码。**
