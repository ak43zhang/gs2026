# 龙头股AI识别方案（基于stock_anomaly盘中异动表）

## 当前数据现状

### stock_anomaly表已有字段

| 字段 | 类型 | 龙头识别价值 |
|------|------|-------------|
| `stock_code` | varchar(10) | 股票代码 |
| `stock_name` | varchar(50) | 股票名称 |
| `anomaly_type` | varchar(20) | 异动类型（zt_hit=首次涨停） |
| `anomaly_time` | time | ⭐⭐⭐ **涨停时间**（判断谁先涨停） |
| `price` | decimal(10,2) | 涨停价格 |
| `change_pct` | decimal(5,2) | 涨跌幅 |
| `continuous_zt` | int | ⭐⭐⭐ **连板数**（判断龙头基因） |
| `mainline_names` | json | ⭐⭐⭐ **关联主线**（按主线分组） |
| `ai_analysis` | text | 已有AI分析结果 |
| `related_industries` | json | 关联行业 |
| `related_concepts` | json | 关联概念 |

### 缺失的关键字段

**stock_anomaly表缺少盘中封单数据**：
- ❌ 封单金额
- ❌ 封单比（封单/流通市值）
- ❌ 开板次数
- ❌ 流通市值

**解决方案**：
1. 从实时行情数据补充（Redis或monitor表）
2. 或用已有字段替代（价格、涨跌幅、连板数）

---

## 重新设计的AI方案

### 核心思路

基于**已有字段** + **AI推理**识别龙头：

```
输入：同主线所有涨停股票（stock_anomaly数据）
      ↓
AI分析：基于涨停时间、连板数、价格、涨跌幅横向比较
      ↓
输出：每只股票的地位（龙头/补涨/跟风）+ 判定依据
```

### 可用字段的龙头识别逻辑

| 字段 | 替代逻辑 |
|------|---------|
| `anomaly_time` | 涨停越早地位越高 |
| `continuous_zt` | 连板数越多越像龙头 |
| `price` | 价格越高可能市值越大（间接判断） |
| `change_pct` | 涨停幅度（10% vs 20%） |
| `mainline_names` | 主线纯度（单主线 vs 多主线） |

### AI判定权重（基于可用字段）

```
龙头股评分 = 
    时间优先度 × 40% +      # anomaly_time越早越高
    连板基因 × 30% +         # continuous_zt越多越高
    主线纯度 × 20% +         # mainline_names越少越纯
    价格强度 × 10%           # price结合change_pct判断
```

---

## 新Prompt设计

```python
LEADER_IDENTIFICATION_PROMPT = """你现在是顶级一线游资，专精龙头股识别与板块情绪分析。

【任务】分析以下同主线涨停股票，识别真龙头、补涨股、跟风股。

【主线信息】
主线名称：{mainline_name}
该主线今日涨停股票数量：{stock_count}只

【涨停股票列表】（按涨停时间排序）
{stocks_list}

【龙头股识别标准】（基于可用数据）

1. 时间优先原则（权重40%）
   - 同主线内，涨停时间越早地位越高
   - 主线内第1只涨停 → 龙头候选
   - 主线内第2-3只涨停 → 补涨候选
   - 主线内第4只以后涨停 → 跟风

2. 连板基因原则（权重30%）
   - continuous_zt（连板数）越高，龙头气质越强
   - 2连板以上 → 确认龙头地位
   - 首板但时间最早 → 潜力龙头

3. 主线纯度原则（权重20%）
   - mainline_names越少，主线纯度越高
   - 单主线（["AI应用"]）> 多主线（["AI应用","半导体"]）
   - 纯度高的更可能是龙头（专注主线）

4. 价格强度原则（权重10%）
   - price越高 + change_pct越大 → 强度越高
   - 科创板/创业板（20%涨停）> 主板（10%涨停）

【输出要求】

对每只股票输出以下JSON：

```json
{{
  "股票代码": "",
  "股票名称": "",
  "涨停时间": "",
  "当前连板数": 0,
  "涨停价格": 0,
  "涨跌幅": 0,
  "关联主线": [],
  "主线内排名": "第X只涨停",
  "主线内地位": "龙头/补涨/跟风/独立",
  "地位判定依据": "基于时间、连板、主线纯度等因素的具体分析",
  "龙头强度评分": 0-100,
  "连板预期": "高/中/低",
  "次日溢价预期": "大幅高开/小幅高开/平开/低开",
  "龙头特征": [
    "特征1：板块内第X只涨停，时间领先",
    "特征2：连板数X板，具备龙头基因",
    "特征3：主线纯度X%，专注度高/低"
  ],
  "风险提示": ""
}}
```

【重要规则】

1. 主线内只能有1-2只龙头，3-5只补涨，其余为跟风
2. 如果某只股票连板数最高但涨停较晚，可能是补涨而非龙头
3. 如果某只股票涨停最早但连板数为0（首板），需结合主线纯度判断
4. 多主线股票（沾边多个概念）通常不是龙头，是跟风补涨
5. 单主线+时间早+连板高 = 真龙头

【示例分析】

主线：AI应用与智能体（5只涨停）

股票A：09:35涨停，连板2天，主线["AI应用"]，价格50元
→ 主线内地位：龙头
→ 判定依据：板块内第1只涨停，2连板确认龙头地位，单主线纯度高
→ 龙头强度评分：95分

股票B：09:42涨停，连板1天，主线["AI应用","半导体"]，价格30元
→ 主线内地位：补涨
→ 判定依据：比龙头晚7分钟，首板，双主线纯度较低
→ 龙头强度评分：65分

股票C：10:15涨停，连板1天，主线["AI应用","半导体","芯片"]，价格20元
→ 主线内地位：跟风
→ 判定依据：涨停时间晚，三主线沾边，被动上涨
→ 龙头强度评分：40分
"""
```

---

## 代码实现

### 1. 数据准备函数

```python
def prepare_mainline_stocks(date: str, min_stocks: int = 3) -> list:
    """
    按主线分组准备涨停股票数据（基于stock_anomaly表）
    
    Args:
        date: 交易日期，如 '2026-06-29'
        min_stocks: 主线最少股票数（少于这个数不分析龙头）
    
    Returns:
        [{mainline_name, stocks: [...]}, ...]
    """
    engine = create_engine(config_util.get_config('common.url'))
    
    sql = f"""
    SELECT 
        stock_code,
        stock_name,
        anomaly_time,
        price,
        change_pct,
        continuous_zt,
        mainline_names,
        related_industries,
        related_concepts
    FROM stock_anomaly 
    WHERE trading_date = '{date}'
      AND anomaly_type = 'zt_hit'
    ORDER BY anomaly_time
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    
    # 解析mainline_names JSON，按主线分组
    mainlines_dict = {}
    
    for _, row in df.iterrows():
        mainlines = json.loads(row['mainline_names']) if row['mainline_names'] else []
        
        for mainline in mainlines:
            if mainline not in mainlines_dict:
                mainlines_dict[mainline] = []
            mainlines_dict[mainline].append(row.to_dict())
    
    # 筛选股票数>=min_stocks的主线
    result = []
    for mainline, stocks in mainlines_dict.items():
        if len(stocks) >= min_stocks:
            # 按时间排序
            stocks_sorted = sorted(stocks, key=lambda x: str(x['anomaly_time']))
            result.append({
                'mainline_name': mainline,
                'stocks': stocks_sorted,
                'count': len(stocks_sorted)
            })
    
    # 按股票数降序排序（主线越强越优先分析）
    result.sort(key=lambda x: x['count'], reverse=True)
    
    return result


def format_stocks_for_prompt(stocks: list) -> str:
    """格式化股票列表为Prompt文本"""
    lines = []
    for i, s in enumerate(stocks, 1):
        mainlines = json.loads(s['mainline_names']) if s['mainline_names'] else []
        mainlines_str = ', '.join(mainlines[:3])  # 最多显示3个主线
        
        lines.append(f"""
{i}. 股票代码：{s['stock_code']}  股票名称：{s['stock_name']}
   涨停时间：{s['anomaly_time']}
   当前连板数：{s['continuous_zt']}板
   涨停价格：{s['price']}元
   涨跌幅：{s['change_pct']}%
   关联主线：[{mainlines_str}]{'...' if len(mainlines) > 3 else ''}
""")
    return '\n'.join(lines)
```

### 2. 批量分析函数

```python
def identify_leaders_by_mainline(date: str, ai_engine: str = 'volcengine') -> list:
    """
    按主线批量识别龙头股
    
    Args:
        date: 交易日期
        ai_engine: AI引擎 'volcengine' 或 'deepseek'
    
    Returns:
        分析结果列表
    """
    mainlines = prepare_mainline_stocks(date)
    results = []
    
    for mainline in mainlines:
        logger.info(f"[龙头股识别] 分析主线: {mainline['mainline_name']} ({mainline['count']}只)")
        
        # 构建Prompt
        prompt = LEADER_IDENTIFICATION_PROMPT.format(
            mainline_name=mainline['mainline_name'],
            stock_count=mainline['count'],
            stocks_list=format_stocks_for_prompt(mainline['stocks'])
        )
        
        # 调用AI
        try:
            if ai_engine == 'volcengine':
                from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import volcengine_analysis
                response = volcengine_analysis(prompt)
            else:
                from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import deepseek_analysis
                response = deepseek_analysis(prompt, _headless=True)
            
            # 解析结果
            result = json.loads(response)
            
            results.append({
                'mainline_name': mainline['mainline_name'],
                'stock_count': mainline['count'],
                'analysis': result,  # AI返回的数组
                'raw_response': response
            })
            
            logger.info(f"[龙头股识别] {mainline['mainline_name']} 分析完成")
            
        except Exception as e:
            logger.error(f"[龙头股识别] {mainline['mainline_name']} 分析失败: {e}")
            continue
    
    return results
```

### 3. 结果存储（新表设计）

```sql
CREATE TABLE IF NOT EXISTS stock_anomaly_leader (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trading_date DATE NOT NULL COMMENT '交易日期',
    mainline_name VARCHAR(100) NOT NULL COMMENT '主线名称',
    stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
    stock_name VARCHAR(50) COMMENT '股票名称',
    anomaly_time TIME COMMENT '涨停时间',
    mainline_rank VARCHAR(20) COMMENT '主线内排名（第X只涨停）',
    mainline_status VARCHAR(20) COMMENT '主线内地位：龙头/补涨/跟风/独立',
    leader_score INT COMMENT '龙头强度评分0-100',
    continuous_expect VARCHAR(10) COMMENT '连板预期：高/中/低',
    next_day_expect VARCHAR(20) COMMENT '次日溢价预期',
    status_reason TEXT COMMENT '地位判定依据',
    leader_features JSON COMMENT '龙头特征数组',
    risk_note TEXT COMMENT '风险提示',
    analysis_json TEXT COMMENT '完整分析JSON',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_date_mainline (trading_date, mainline_name),
    INDEX idx_date_code (trading_date, stock_code),
    INDEX idx_status (mainline_status),
    INDEX idx_score (leader_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='盘中异动龙头股识别结果';
```

### 4. 保存结果函数

```python
def save_leader_identification(results: list, date: str):
    """存储龙头股识别结果"""
    engine = create_engine(config_util.get_config('common.url'))
    
    records = []
    for r in results:
        for stock in r['analysis']:  # AI返回的是数组
            records.append({
                'trading_date': date,
                'mainline_name': r['mainline_name'],
                'stock_code': stock['股票代码'],
                'stock_name': stock['股票名称'],
                'anomaly_time': stock['涨停时间'],
                'mainline_rank': stock['主线内排名'],
                'mainline_status': stock['主线内地位'],
                'leader_score': stock['龙头强度评分'],
                'continuous_expect': stock['连板预期'],
                'next_day_expect': stock['次日溢价预期'],
                'status_reason': stock['地位判定依据'],
                'leader_features': json.dumps(stock.get('龙头特征', []), ensure_ascii=False),
                'risk_note': stock.get('风险提示', ''),
                'analysis_json': json.dumps(stock, ensure_ascii=False),
                'created_at': datetime.now()
            })
    
    if not records:
        logger.warning("[龙头股识别] 无结果需要保存")
        return
    
    df = pd.DataFrame(records)
    
    with engine.connect() as conn:
        # 先删除该日期的旧数据
        conn.execute(text(f"""
            DELETE FROM stock_anomaly_leader 
            WHERE trading_date = '{date}'
        """))
        conn.commit()
        
        # 插入新数据
        df.to_sql('stock_anomaly_leader', conn, if_exists='append', index=False)
        conn.commit()
    
    logger.info(f"[龙头股识别] 保存完成：{len(records)}条记录")
```

### 5. 集成到现有流程

修改 `anomaly_analyzer.py` 或新增独立任务：

```python
def leader_identification_task(date: str = None):
    """龙头股识别定时任务"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    logger.info(f"[龙头股识别] 开始分析 {date}")
    
    # 1. 识别龙头股
    results = identify_leaders_by_mainline(date)
    
    # 2. 保存结果
    save_leader_identification(results, date)
    
    # 3. 输出摘要
    for r in results:
        leaders = [s for s in r['analysis'] if s['主线内地位'] == '龙头']
        logger.info(f"[龙头股识别] {r['mainline_name']}: {len(leaders)}只龙头, {r['stock_count']}只总涨停")
    
    logger.info(f"[龙头股识别] 完成")


# 可以添加到定时任务（每5分钟运行一次）
if __name__ == '__main__':
    leader_identification_task()
```

---

## 实施步骤

### 阶段1：创建表（5分钟）
```sql
-- 执行上述CREATE TABLE语句
```

### 阶段2：新增代码文件（30分钟）
```
src/gs2026/analysis/worker/realtime/leader_identifier.py
- prepare_mainline_stocks()
- identify_leaders_by_mainline()
- save_leader_identification()
- leader_identification_task()
```

### 阶段3：新增Prompt（10分钟）
```
src/gs2026/analysis/worker/message/prompts.py
- LEADER_IDENTIFICATION_PROMPT
```

### 阶段4：集成到现有流程（15分钟）
```
修改 anomaly_analyzer.py 或新增独立任务
```

### 阶段5：测试验证（30分钟）
```python
# 测试AI应用与智能体主线
results = identify_leaders_by_mainline('2026-06-29')
# 验证32只股票中是否识别出1-2只龙头
```

**总耗时：约1.5小时**

---

## 预期效果

**AI应用与智能体主线（32只涨停）**

| 地位 | 数量 | 特征 |
|------|------|------|
| 龙头 | 1-2只 | 09:25-09:35涨停，单主线，可能已有连板 |
| 补涨 | 3-5只 | 09:35-10:00涨停，1-2个主线 |
| 跟风 | 其余 | 10:00后涨停，多主线沾边 |

**输出示例**：
```json
{
  "股票代码": "600228",
  "股票名称": "返利科技",
  "主线内地位": "龙头",
  "龙头强度评分": 92,
  "判定依据": "09:25最早涨停，单主线[AI应用与智能体]纯度高，科创板20%涨停强度大"
}
```
