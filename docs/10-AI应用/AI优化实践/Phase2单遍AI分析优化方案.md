# Phase2优化方案（单遍AI分析）

## 用户核心诉求

**当前问题**：
- 方案B需要走两遍AI分析
  - 第1遍：当前股票的基础分析（Phase 1）
  - 第2遍：主线成型后的横向比较（改进的Phase 2）
- **希望：只走一遍AI分析就能出准确结果**

---

## 优化思路

### 核心问题分析

**为什么当前需要两遍？**

```
第1遍（Phase 1）：
- 输入：单只股票
- 输出：异动原因、板块、概念
- 问题：不知道同主线其他股票，无法判定role

第2遍（改进Phase 2）：
- 输入：当前股票 + 当日所有涨停 + 已识别主线
- 输出：主线归属 + role
- 问题：增量分析，早期股票role可能错误
```

**根本原因**：
- Phase 1和Phase 2是**串行**的
- Phase 1完成才能进入Phase 2
- 导致：早期股票分析时，主线信息不完整

---

## 优化方案：合并分析（推荐）

### 核心思路

**将Phase 1和Phase 2合并为一次AI分析**：

```
原流程：
Phase 1（单只分析）→ Phase 2（关联分析）
   ↓                    ↓
  2次AI调用            role可能错误

新流程：
合并分析（一次AI调用）
   ↓
  输出：异动原因 + 主线归属 + role（基于当前所有信息）
```

### 具体实现

**修改 `analyze_one()` 函数**：

```python
def analyze_one_v2(engine, anomaly, bk_dic_str, gn_dic_str, redis_client):
    """
    改进版：一次AI分析输出完整结果（异动原因 + 主线归属 + role）
    """
    anomaly_id = anomaly['id']
    stock_code = anomaly['stock_code']
    trading_date = str(anomaly['trading_date'])
    
    # 1. 获取当日所有涨停（用于主线判断）
    all_zt = _get_today_all_zt(engine, trading_date, anomaly_id)
    
    # 2. 获取已识别主线
    existing_mainlines = _get_existing_mainlines(engine, trading_date)
    
    # 3. 构建合并Prompt（一次分析所有内容）
    prompt = build_unified_prompt(anomaly, all_zt, existing_mainlines, bk_dic_str, gn_dic_str)
    
    # 4. 一次AI分析
    response = _call_ai(prompt)
    
    # 5. 解析结果（包含异动原因 + 主线归属 + role）
    analysis = parse_unified_response(response)
    
    # 6. 更新stock_anomaly（异动原因）
    _update_anomaly_analysis(engine, anomaly_id, analysis['异动分析'])
    
    # 7. 更新主线和role（主线归属）
    _update_mainlines_v2(engine, anomaly_id, trading_date, anomaly, analysis['主线归属'])
    
    return True
```

### 合并Prompt设计

```python
def build_unified_prompt(anomaly: dict, all_zt: list, existing_mainlines: str,
                         bk_dic_str: str, gn_dic_str: str) -> str:
    """
    构建合并分析Prompt
    - 输入：当前股票 + 当日所有涨停 + 已识别主线
    - 输出：异动原因 + 主线归属 + role（基于当前完整信息）
    """
    
    stock_code = anomaly['stock_code']
    stock_name = anomaly['stock_name']
    anomaly_time = anomaly['anomaly_time']
    
    # 构建当日涨停摘要
    zt_summary = _build_zt_summary_for_prompt(all_zt)
    
    return f"""你现在是顶级一线游资专属量化风控分析师。

【任务】分析当前股票的异动原因，并判定其在主线中的role。

【当前股票】
股票代码：{stock_code}
股票名称：{stock_name}
涨停时间：{anomaly_time}

【当日涨停股票列表】（按时间排序）
{zt_summary}

【已识别主线】
{existing_mainlines}

【分析要求】

1. 异动分析（35%权重）
   - 异动原因：具体驱动逻辑
   - 板块消息：涉及板块及刺激消息
   - 概念消息：涉及概念及刺激消息
   - 消息类型：利好/利空/中性
   - 影响力度：高/中/低

2. 主线归属分析（65%权重）
   - 是否归属已有主线？
   - 是否形成新主线？
   - 是否为独立个股？
   
   【关键】role判定必须基于同主线所有股票的横向比较：
   - 主线内第1只涨停 → 龙头（但需看后续是否有更强逻辑的股票）
   - 逻辑最正宗 + 涨停较早 → 龙头
   - 涨停较晚 + 逻辑沾边 → 跟风
   - 涨停较晚 + 有一定逻辑 → 补涨

【输出格式】
必须返回以下JSON：

```json
{{
  "异动分析": {{
    "异动原因": "",
    "板块消息": [{{"板块": "", "消息": ""}}],
    "概念消息": [{{"概念": "", "消息": ""}}],
    "消息类型": "利好/利空/中性",
    "影响力度": "高/中/低",
    "原因置信度": "高/中/低",
    "资金动向": "",
    "股性分析": ""
  }},
  
  "主线归属": [{{
    "type": "existing/new/independent",
    "mainline_name": "主线名称",
    "mainline_reason": "驱动逻辑",
    "catalyst": "催化事件",
    "role": "龙头/跟风/补涨",
    "role_reason": "判定依据：基于同主线X只股票的横向比较，该股票...",
    "confidence_delta": 15,
    "evidence": "归属证据"
  }}],
  
  "预判": {{
    "预判吻合度": "",
    "预期涨停消息": []
  }}
}}
```

【重要规则】

1. role判定必须基于横向比较：
   - 查看"当日涨停股票列表"中同主线的股票
   - 比较涨停时间、逻辑正宗性、连板数
   - 给出准确的role和理由

2. 如果当前股票是主线内第1只：
   - 暂时标记为"龙头"（但注明"待确认，看后续是否有更强逻辑股票"）
   - 或者标记为"潜在龙头"

3. 如果主线已有其他股票：
   - 必须横向比较后判定role
   - 不能随意标记为"龙头"

4. 主线内只能有1-2只龙头
"""
```

### 关键改进点

**改进1：Prompt中提供完整信息**
- 当前股票
- **当日所有涨停**（用于横向比较）
- **已识别主线**（用于归属判断）

**改进2：AI一次输出完整结果**
- 异动原因
- 主线归属
- **role（基于横向比较）**

**改进3：role判定更准确**
- AI可以看到同主线其他股票
- 基于时间、逻辑、连板数横向比较
- 给出准确的role和理由

---

## 进一步优化：延迟修正机制

### 问题

即使合并分析，**早期股票的role仍可能不准确**：
- 第1只股票分析时，主线只有1只，只能标记为"潜在龙头"
- 后续股票分析时，主线成型，但第1只股票的role不会自动更新

### 解决方案：轻量级延迟修正

**不增加AI调用，只修正role字段**：

```python
def _update_mainlines_v3(engine, anomaly_id: int, trading_date: str,
                         anomaly_data: dict, mainline_results: list):
    """
    优化版：更新主线时，轻量级修正同主线所有股票的role
    - 不增加AI调用
    - 基于规则重新计算role
    """
    for ml in mainline_results:
        if ml['type'] == 'independent':
            continue
            
        mainline_id = hashlib.md5(f"{ml['name']}_{trading_date}".encode()).hexdigest()
        
        # 1. 先更新当前股票（保持原有行为）
        update_single_stock_role(engine, anomaly_id, mainline_id, 
                                ml['role'], ml.get('evidence', ''))
        
        # 2. 获取该主线所有股票
        all_stocks = get_mainline_all_stocks(engine, mainline_id, trading_date)
        
        if len(all_stocks) < 2:
            continue
        
        # 3. 【关键】基于规则重新计算role（无AI调用）
        # 规则：
        # - 第1只涨停 + 逻辑正宗 → 龙头
        # - 涨停较早 + 有一定逻辑 → 补涨
        # - 涨停较晚 + 逻辑沾边 → 跟风
        
        # 按时间排序
        sorted_stocks = sorted(all_stocks, key=lambda x: x['anomaly_time'])
        
        # 重新分配role
        for i, stock in enumerate(sorted_stocks):
            if i == 0:
                # 第1只：龙头（如果逻辑正宗）
                new_role = '龙头'
            elif i <= 2:
                # 第2-3只：补涨
                new_role = '补涨'
            else:
                # 第4只以后：跟风
                new_role = '跟风'
            
            # 更新role（如果发生变化）
            if stock.get('role') != new_role:
                update_stock_role(engine, stock['anomaly_id'], mainline_id, new_role)
                logger.info(f"[role修正] {stock['stock_code']} {stock['stock_name']} "
                           f"{stock.get('role')} -> {new_role}")
```

### 规则细化（可选AI辅助）

**如果规则不够准确，可以用轻量级AI**：

```python
def recalculate_roles_with_light_ai(all_stocks: list) -> list:
    """
    轻量级AI重新计算role
    - 输入：同主线所有股票（已排序）
    - 输出：每只股票的新role
    - 特点：Prompt简单，AI调用快
    """
    
    # 构建轻量级Prompt
    prompt = f"""基于以下同主线涨停股票，重新判定每只股票的role。

股票列表（按涨停时间排序）：
{format_stocks_simple(all_stocks)}

判定规则：
1. 主线内第1只涨停 + 逻辑正宗 → 龙头
2. 涨停较早（前3只）+ 有一定逻辑 → 补涨  
3. 涨停较晚（第4只以后）+ 逻辑沾边 → 跟风
4. 主线内只能有1-2只龙头

输出JSON数组：
[{{"anomaly_id": 1, "role": "龙头/跟风/补涨", "reason": ""}}, ...]
"""
    
    response = _call_ai(prompt)
    return parse_response(response)
```

---

## 方案对比

| 方案 | AI调用次数 | role准确性 | 复杂度 | 推荐度 |
|------|-----------|-----------|--------|--------|
| 原方案（两遍） | 2次/股票 | 低 | 低 | ⭐⭐ |
| **合并分析（推荐）** | **1次/股票** | **中** | **中** | **⭐⭐⭐** |
| 合并+延迟修正 | 1次/股票 + 轻量修正 | 高 | 中 | ⭐⭐⭐ |

---

## 推荐方案：合并分析 + 轻量级延迟修正

### 核心流程

```
analyze_one_v2() 改进版
    ↓
1. 获取当日所有涨停 + 已识别主线
    ↓
2. 合并Prompt（一次AI分析）
    ↓
3. AI输出：异动原因 + 主线归属 + role
    ↓
4. 更新stock_anomaly（异动原因）
    ↓
5. 更新主线和当前股票role
    ↓
6. 【轻量级修正】重新计算同主线所有role
   - 基于规则（无AI调用）
   - 或轻量级AI（简单Prompt）
```

### 实施步骤（约1.5小时）

| 步骤 | 耗时 |
|------|------|
| 修改 `analyze_one()` → `analyze_one_v2()` | 30分钟 |
| 新增 `build_unified_prompt()` | 20分钟 |
| 修改 `_update_mainlines()` → 轻量级修正 | 20分钟 |
| 测试验证 | 20分钟 |
| **总计** | **约1.5小时** |

### 预期效果

- **AI调用次数**：从2次/股票 → 1次/股票（节省50%）
- **role准确性**：基于横向比较，更准确
- **主线成型后**：轻量级修正，确保role正确

---

## 结论

**方案可行！**

**推荐：合并分析 + 轻量级延迟修正**
- 只走一遍AI分析（节省50%调用）
- role基于横向比较，更准确
- 轻量级修正机制，确保主线成型后role正确

**确认后我立即实施。**
