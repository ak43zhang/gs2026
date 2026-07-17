# 龙头股AI识别方案（纯Prompt方案，无需额外数据）

## 可行性分析

### 当前已有字段（ztb_day表）

| 字段名 | 用途 | 龙头识别价值 |
|--------|------|-------------|
| `首次涨停时间` | 判断谁先涨停 | ⭐⭐⭐ 核心字段 |
| `涨停封单额` | 封单金额 | ⭐⭐⭐ 核心字段 |
| `涨停封流比` | 封单/流通市值 | ⭐⭐⭐ 核心字段（已有封单比！）|
| `连续涨停天数` | 当前连板数 | ⭐⭐⭐ 核心字段 |
| `a股流通市值` | 流通市值 | ⭐⭐ 辅助字段 |
| `涨停原因类别` | 板块归属 | ⭐⭐⭐ 核心字段 |
| `涨停开板次数` | 封板质量 | ⭐⭐ 辅助字段 |
| `几天几板` | 连板标识 | ⭐⭐ 辅助字段 |

**结论：已有足够数据支持AI识别龙头！**

---

## 方案设计：增强ZTB Prompt

### 核心思路

不修改数据库，不增加字段，**纯通过Prompt改造**让AI识别龙头：

1. **批量输入**：一次性给AI同板块的所有涨停股票
2. **横向比较**：让AI基于已有字段比较判定地位
3. **明确输出**：要求AI输出"板块内地位"和"龙头判定依据"

---

## 新Prompt设计

```python
ENHANCED_ZTB_PROMPT = """你现在是顶级一线游资，专精龙头股识别与短线博弈。

【任务】分析以下涨停股票，识别板块内的真龙头、补涨股、跟风股。

【板块信息】
板块名称：{block_name}
板块涨停股票数量：{block_count}只

【涨停股票列表】（按首次涨停时间排序）
{stocks_list}

【龙头股识别标准】

1. 时间优先原则（权重40%）
   - 同板块内，首次涨停时间越早地位越高
   - 板块内第1只涨停 → 龙头候选
   - 板块内第2-3只涨停 → 补涨候选
   - 板块内第4只以后涨停 → 跟风

2. 封单强度原则（权重30%）
   - 涨停封流比 > 10% → 绝对强势
   - 涨停封流比 5-10% → 强势
   - 涨停封流比 < 5% → 弱势
   - 封单额越大，龙头气质越强

3. 连板基因原则（权重20%）
   - 连续涨停天数越多，龙头地位越稳
   - 2板以上且封单强 → 确认龙头
   - 首板但封单极强+时间最早 → 潜力龙头

4. 封板质量原则（权重10%）
   - 涨停开板次数越少越好
   - 开板0次 > 开板1次 > 开板多次

【输出要求】

对每只股票输出以下字段：

```json
{{
  "股票代码": "",
  "股票名称": "",
  "首次涨停时间": "",
  "涨停封单额": "",
  "涨停封流比": "",
  "连续涨停天数": "",
  "涨停开板次数": "",
  "板块内排名": "第X只涨停",
  "板块内地位": "龙头/补涨/跟风/独立",
  "地位判定依据": "基于时间、封单、连板等因素的具体分析",
  "龙头强度评分": "0-100分",
  "连板预期": "高/中/低",
  "次日溢价预期": "大幅高开/小幅高开/平开/低开",
  "股性分析": "",
  "龙虎榜分析": "",
  "板块消息": [{{"板块": "", "板块刺激消息": [""]}}],
  "概念消息": [{{"概念": "", "概念刺激消息": [""]}}],
  "龙头股消息": [{{"龙头股": "", "龙头股刺激消息": [""]}}],
  "消息": [{{"影响消息": "", "最早出现时间": ""}}],
  "预期涨停消息": [{{"预期消息": "", "最早出现时间": "", "延续性": ""}}],
  "深度分析": [""]
}}
```

【重要】
1. 必须基于"首次涨停时间"判断谁先谁后
2. 必须基于"涨停封流比"判断封单强度
3. 板块内只能有1-2只龙头，3-5只补涨，其余为跟风
4. 如果某只股票封单极强但涨停较晚，可能是补涨而非龙头
5. 如果某只股票涨停最早但封单极弱，可能是试盘失败

【示例】
板块：AI应用（5只涨停）

股票A：首次涨停 09:35:00，封流比 15%，连板2天，开板0次
→ 板块内地位：龙头
→ 判定依据：板块内第1只涨停，封流比15%极强，2连板确认龙头地位

股票B：首次涨停 09:42:00，封流比 8%，连板1天，开板1次
→ 板块内地位：补涨
→ 判定依据：比龙头晚7分钟，封单中等，首板跟随上涨

股票C：首次涨停 10:15:00，封流比 3%，连板1天，开板2次
→ 板块内地位：跟风
→ 判定依据：涨停时间晚，封单弱，多次开板，被动上涨
"""
```

---

## 代码实现

### 1. 数据准备函数

```python
def prepare_block_stocks(date: str, min_stocks: int = 3) -> list:
    """
    按板块分组准备涨停股票数据
    
    Args:
        date: 交易日期，如 '20260629'
        min_stocks: 板块最少股票数（少于这个数不分析龙头）
    
    Returns:
        [{block_name, stocks: [...]}, ...]
    """
    engine = create_engine(config_util.get_config('common.url'))
    
    sql = f"""
    SELECT 
        股票代码,
        股票简称,
        首次涨停时间,
        涨停封单额,
        涨停封流比,
        连续涨停天数,
        涨停开板次数,
        a股流通市值,
        涨停原因类别,
        几天几板
    FROM ztb_day 
    WHERE trade_date = '{date}'
      AND 涨停 = '涨停'
    ORDER BY 首次涨停_time
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    
    # 按板块分组
    blocks = []
    for block_name, group in df.groupby('涨停原因类别'):
        if len(group) >= min_stocks:  # 只分析有3只以上涨停的板块
            stocks = group.to_dict('records')
            blocks.append({
                'block_name': block_name,
                'stocks': stocks,
                'count': len(stocks)
            })
    
    return blocks


def format_stocks_list(stocks: list) -> str:
    """格式化股票列表为Prompt文本"""
    lines = []
    for i, s in enumerate(stocks, 1):
        lines.append(f"""
{i}. 股票代码：{s['股票代码']}  股票简称：{s['股票简称']}
   首次涨停时间：{s['首次涨停时间']}
   涨停封单额：{s['涨停封单额']}万
   涨停封流比：{s['涨停封流比']}%
   连续涨停天数：{s['连续涨停天数']}天
   涨停开板次数：{s['涨停开板次数']}次
   a股流通市值：{s['a股流通市值']}亿
   几天几板：{s['几天几板']}
""")
    return '\n'.join(lines)
```

### 2. 批量分析函数

```python
def analyze_leaders_by_block(date: str, ai_engine: str = 'volcengine') -> list:
    """
    按板块批量分析龙头股
    
    Args:
        date: 交易日期
        ai_engine: AI引擎 'volcengine' 或 'deepseek'
    
    Returns:
        分析结果列表
    """
    blocks = prepare_block_stocks(date)
    results = []
    
    for block in blocks:
        # 构建Prompt
        prompt = ENHANCED_ZTB_PROMPT.format(
            block_name=block['block_name'],
            block_count=block['count'],
            stocks_list=format_stocks_list(block['stocks'])
        )
        
        # 调用AI
        if ai_engine == 'volcengine':
            from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import volcengine_analysis
            response = volcengine_analysis(prompt)
        else:
            from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import deepseek_analysis
            response = deepseek_analysis(prompt, _headless=True)
        
        # 解析结果
        try:
            result = json.loads(response)
            results.append({
                'block_name': block['block_name'],
                'analysis': result,
                'raw_response': response
            })
        except json.JSONDecodeError:
            logger.error(f"解析失败: {block['block_name']}")
            continue
    
    return results
```

### 3. 结果存储

```python
def save_leader_analysis(results: list, date: str):
    """存储龙头股分析结果"""
    engine = create_engine(config_util.get_config('common.url'))
    
    records = []
    for r in results:
        for stock in r['analysis']:  # AI返回的是数组
            records.append({
                'trade_date': date,
                'block_name': r['block_name'],
                'stock_code': stock['股票代码'],
                'stock_name': stock['股票名称'],
                'block_rank': stock['板块内排名'],
                'block_status': stock['板块内地位'],  # 龙头/补涨/跟风
                'leader_score': stock['龙头强度评分'],
                'continuous_expect': stock['连板预期'],
                'next_day_expect': stock['次日溢价预期'],
                'status_reason': stock['地位判定依据'],
                'analysis_json': json.dumps(stock, ensure_ascii=False),
                'created_at': datetime.now()
            })
    
    df = pd.DataFrame(records)
    with engine.connect() as conn:
        df.to_sql('ztb_leader_analysis', conn, if_exists='append', index=False)
```

---

## 新表设计

```sql
CREATE TABLE IF NOT EXISTS ztb_leader_analysis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trade_date VARCHAR(8) NOT NULL COMMENT '交易日期',
    block_name VARCHAR(100) NOT NULL COMMENT '板块名称',
    stock_code VARCHAR(10) NOT NULL COMMENT '股票代码',
    stock_name VARCHAR(50) COMMENT '股票简称',
    block_rank VARCHAR(20) COMMENT '板块内排名（第X只涨停）',
    block_status VARCHAR(20) COMMENT '板块内地位：龙头/补涨/跟风/独立',
    leader_score INT COMMENT '龙头强度评分0-100',
    continuous_expect VARCHAR(10) COMMENT '连板预期：高/中/低',
    next_day_expect VARCHAR(20) COMMENT '次日溢价预期',
    status_reason TEXT COMMENT '地位判定依据',
    analysis_json TEXT COMMENT '完整分析JSON',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date_block (trade_date, block_name),
    INDEX idx_date_code (trade_date, stock_code),
    INDEX idx_status (block_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='涨停龙头股分析结果';
```

---

## 方案优势

| 优势 | 说明 |
|------|------|
| **零数据成本** | 不增加任何字段，纯用已有数据 |
| **可解释性强** | AI明确输出判定依据，可追溯 |
| **灵活可调** | 调整Prompt即可改变识别逻辑 |
| **批量处理** | 一次分析整个板块，效率高 |
| **可验证** | 板块内地位可以次日验证 |

---

## 预期效果

**改进前**：
- 输入：单只股票信息
- 输出：该股票的涨停原因
- 问题：32只股票各自独立，无龙头概念

**改进后**：
- 输入：同板块所有涨停股票（批量）
- 输出：每只股票的地位（龙头/补涨/跟风）+ 判定依据
- 效果：32只股票 → 按板块分组 → 每组识别1-2只龙头

---

## 实施步骤

1. **创建新表** `ztb_leader_analysis`（5分钟）
2. **新增Prompt** `ENHANCED_ZTB_PROMPT`（10分钟）
3. **新增函数** `prepare_block_stocks`、`analyze_leaders_by_block`（20分钟）
4. **集成到现有流程**（15分钟）
5. **测试验证**（30分钟）

**总耗时：约1.5小时**
