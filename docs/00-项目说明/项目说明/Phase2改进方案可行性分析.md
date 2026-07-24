# Phase 2改进方案可行性分析

## 用户核心诉求

**不增加Phase 3，直接在Phase 2改进**：
1. 当主线确定后（existing或new）
2. 获取该主线**所有**股票
3. 横向比较，重新细分role
4. 更新到每个股票的`stock_anomaly_mainline_rel.role`

---

## 当前Phase 2流程

```python
def analyze_correlation(engine, anomaly, bk_dic_str, gn_dic_str, redis_client):
    # 1. 获取当日所有涨停
    all_zt = _get_today_all_zt(engine, trading_date, anomaly_id)
    
    # 2. 获取已识别主线
    existing_mainlines = _get_existing_mainlines(engine, trading_date)
    
    # 3. 构建Prompt（当前股票+所有涨停+已识别主线）
    prompt = build_correlation_prompt(...)
    
    # 4. AI分析
    response = _call_ai(prompt)
    
    # 5. 解析结果
    mainline_results = analysis.get('主线归属', [])
    
    # 6. 更新主线表和关系表
    _update_mainlines(engine, anomaly_id, trading_date, anomaly_data, mainline_results)
```

**当前问题**：
- `_update_mainlines()` 只更新当前股票的role
- 不重新计算同主线其他股票的role

---

## 改进方案

### 方案A：修改 `_update_mainlines()`（推荐）

**改进点**：
```python
def _update_mainlines_v2(engine, anomaly_id: int, trading_date: str, 
                         anomaly_data: dict, mainline_results: list):
    """
    改进版：更新主线时，重新计算该主线所有股票的role
    """
    for ml in mainline_results:
        if ml['type'] == 'independent':
            continue
            
        mainline_id = hashlib.md5(f"{ml['name']}_{trading_date}".encode()).hexdigest()
        
        # 1. 获取该主线所有股票（包括当前股票）
        all_stocks = get_mainline_all_stocks(engine, mainline_id, trading_date)
        
        if len(all_stocks) < 2:
            # 只有1只，直接标记为龙头
            update_single_stock_role(engine, anomaly_id, mainline_id, '龙头')
            continue
        
        # 2. AI横向比较分析（新Prompt）
        comparison_result = ai_compare_mainline_stocks(all_stocks)
        # 返回：每只股票的新role和评分
        
        # 3. 批量更新该主线所有股票的role
        for stock in comparison_result:
            update_stock_role(engine, stock['anomaly_id'], mainline_id, 
                            stock['role'], stock['score'])
```

**优点**：
- 不增加新Phase
- 每次分析都重新计算该主线所有role
- 数据一致性最好

**缺点**：
- AI调用次数增加（每次分析都重新比较）
- 主线股票多时，Prompt很长

---

### 方案B：延迟批量更新（平衡）

**改进点**：
```python
def _update_mainlines_v3(engine, anomaly_id: int, trading_date: str,
                         anomaly_data: dict, mainline_results: list):
    """
    平衡版：主线股票数>=3时才批量重新计算
    """
    for ml in mainline_results:
        if ml['type'] == 'independent':
            continue
            
        mainline_id = ...
        
        # 1. 先按当前逻辑更新（保持原有行为）
        update_single_stock_role(engine, anomaly_id, mainline_id, ml['role'])
        
        # 2. 检查主线股票数
        stock_count = get_mainline_stock_count(engine, mainline_id, trading_date)
        
        # 3. 当主线成型（>=3只）时，批量重新计算
        if stock_count >= 3:
            all_stocks = get_mainline_all_stocks(engine, mainline_id, trading_date)
            
            # 异步或同步批量重新计算
            comparison_result = ai_compare_mainline_stocks(all_stocks)
            
            # 批量更新
            for stock in comparison_result:
                update_stock_role(engine, stock['anomaly_id'], mainline_id,
                                stock['role'], stock['score'])
```

**优点**：
- 主线成型后才重新计算（避免频繁AI调用）
- 不增加新Phase
- 数据较准确

**缺点**：
- 第3只股票分析时，会触发前2只的role重新计算
- 有一定延迟

---

### 方案C：定时批量更新（异步）

**改进点**：
```python
# 在anomaly_analyzer.py中新增定时任务

def batch_update_leader_roles(engine, trading_date: str):
    """
    定时任务：每5分钟检查主线，批量更新role
    """
    # 1. 获取当日所有成型主线（stock_count >= 3）
    mainlines = get_formed_mainlines(engine, trading_date)
    
    for mainline in mainlines:
        # 2. 获取该主线所有股票
        all_stocks = get_mainline_all_stocks(engine, mainline['id'], trading_date)
        
        # 3. 检查是否需要更新（最后更新时间>5分钟）
        if needs_update(mainline):
            # 4. AI横向比较
            comparison_result = ai_compare_mainline_stocks(all_stocks)
            
            # 5. 批量更新
            for stock in comparison_result:
                update_stock_role(engine, stock['anomaly_id'], mainline['id'],
                                stock['role'], stock['score'])
```

**优点**：
- 不修改Phase 2核心逻辑
- 异步更新，不影响实时分析
- 可控制更新频率

**缺点**：
- 需要新增定时任务
- 有一定延迟

---

## 可行性对比

| 维度 | 方案A（立即更新） | 方案B（延迟更新） | 方案C（定时更新） |
|------|------------------|------------------|------------------|
| **实现复杂度** | ⭐⭐ 中 | ⭐⭐ 中 | ⭐⭐⭐ 较高 |
| **数据准确性** | ⭐⭐⭐ 高 | ⭐⭐⭐ 高 | ⭐⭐⭐ 高 |
| **AI调用次数** | ⭐⭐⭐ 多 | ⭐⭐ 中 | ⭐⭐ 中 |
| **实时性** | ⭐⭐⭐ 立即 | ⭐⭐ 延迟 | ⭐⭐ 延迟 |
| **代码侵入性** | ⭐⭐ 中 | ⭐⭐ 中 | ⭐ 低 |
| **推荐度** | ⭐⭐⭐ 推荐 | ⭐⭐⭐ 推荐 | ⭐⭐ 备选 |

---

## 推荐方案：方案B（延迟批量更新）

### 理由

1. **不增加Phase**：符合用户要求
2. **主线成型后更新**：避免频繁AI调用
3. **数据准确**：横向比较识别真龙头
4. **实现简单**：修改 `_update_mainlines()` 即可

### 实施步骤

```python
def _update_mainlines_v2(engine, anomaly_id: int, trading_date: str,
                         anomaly_data: dict, mainline_results: list):
    """
    改进版_update_mainlines：主线成型后批量重新计算role
    """
    import hashlib
    
    for ml in mainline_results:
        ml_type = ml.get('type', 'independent')
        ml_name = ml.get('mainline_name', '独立个股')
        
        if ml_type == 'independent':
            mainline_names_list.append('独立个股')
            continue
        
        # 生成主线ID
        mainline_id = hashlib.md5(f"{ml_name}_{trading_date}".encode()).hexdigest()
        mainline_names_list.append(ml_name)
        
        # ===== 改进点1：先按当前逻辑更新当前股票 =====
        ml_role = ml.get('role', '跟风')
        ml_evidence = ml.get('evidence', '')
        ml_confidence_delta = ml.get('confidence_delta', 15)
        
        # 插入当前股票的关系（保持原有行为）
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO stock_anomaly_mainline_rel 
                (anomaly_id, mainline_id, role, evidence, confidence_contribution, created_at)
                VALUES (:aid, :mid, :role, :evidence, :conf, NOW())
                ON DUPLICATE KEY UPDATE
                role = VALUES(role),
                evidence = VALUES(evidence),
                confidence_contribution = VALUES(confidence_contribution)
            """), {
                'aid': anomaly_id,
                'mid': mainline_id,
                'role': ml_role,
                'evidence': ml_evidence,
                'conf': ml_confidence_delta
            })
            conn.commit()
        
        # ===== 改进点2：检查主线是否成型（>=3只） =====
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM stock_anomaly_mainline_rel
                WHERE mainline_id = :mid
            """), {'mid': mainline_id})
            stock_count = result.fetchone()[0]
        
        # ===== 改进点3：主线成型后，批量重新计算所有role =====
        if stock_count >= 3:
            logger.info(f"[主线龙头识别] 主线 {ml_name} 已成型({stock_count}只)，重新计算role...")
            
            # 3.1 获取该主线所有股票
            all_stocks = get_mainline_all_stocks(engine, mainline_id, trading_date)
            
            # 3.2 AI横向比较分析（新Prompt）
            comparison_result = ai_compare_mainline_stocks(ml_name, all_stocks)
            
            # 3.3 批量更新所有股票的role
            with engine.connect() as conn:
                for stock in comparison_result:
                    conn.execute(text("""
                        UPDATE stock_anomaly_mainline_rel
                        SET role = :role,
                            confidence_contribution = :score
                        WHERE anomaly_id = :aid AND mainline_id = :mid
                    """), {
                        'aid': stock['anomaly_id'],
                        'mid': mainline_id,
                        'role': stock['role'],
                        'score': stock['score']
                    })
                conn.commit()
            
            logger.info(f"[主线龙头识别] 主线 {ml_name} role更新完成")
```

### 新增函数

```python
def get_mainline_all_stocks(engine, mainline_id: str, trading_date: str) -> list:
    """获取主线所有股票"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                a.id as anomaly_id,
                a.stock_code,
                a.stock_name,
                a.anomaly_time,
                a.continuous_zt,
                a.price,
                a.change_pct,
                r.role,
                r.evidence
            FROM stock_anomaly_mainline_rel r
            JOIN stock_anomaly a ON r.anomaly_id = a.id
            WHERE r.mainline_id = :mid
              AND a.trading_date = :date
            ORDER BY a.anomaly_time
        """), {'mid': mainline_id, 'date': trading_date})
        
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]


def ai_compare_mainline_stocks(mainline_name: str, stocks: list) -> list:
    """
    AI横向比较分析主线内所有股票
    
    Returns:
        [{'anomaly_id': 1, 'role': '龙头', 'score': 95}, ...]
    """
    # 构建Prompt
    prompt = build_mainline_comparison_prompt(mainline_name, stocks)
    
    # AI分析
    response = _call_ai(prompt)
    
    # 解析结果
    analysis = json.loads(response)
    
    return analysis.get('股票列表', [])


def build_mainline_comparison_prompt(mainline_name: str, stocks: list) -> str:
    """构建主线横向比较Prompt"""
    stocks_text = '\n'.join([
        f"{i+1}. {s['stock_code']} {s['stock_name']} | "
        f"涨停时间：{s['anomaly_time']} | "
        f"连板：{s['continuous_zt']}板 | "
        f"当前role：{s['role']}"
        for i, s in enumerate(stocks)
    ])
    
    return f"""你现在是顶级一线游资，专精龙头股识别。

【任务】对以下同主线涨停股票进行横向比较，重新判定每只股票的role。

【主线名称】{mainline_name}
【涨停股票】（按时间排序）：
{stocks_text}

【判定标准】
1. 时间优先：主线内第1只涨停 → 龙头
2. 连板基因：continuous_zt越高，龙头气质越强
3. 逻辑正宗：主营业务与主线相关度

【输出要求】
返回JSON数组：
```json
[
  {{"anomaly_id": 1, "stock_code": "", "stock_name": "", "role": "龙头/跟风/补涨", "score": 0-100, "reason": ""}},
  ...
]
```

【重要】
- 主线内只能有1-2只龙头
- 必须有明确的判定依据
- score 0-100，龙头>80，补涨60-80，跟风<60
"""
```

---

## 结论

**方案可行！**

**推荐方案B（延迟批量更新）**：
- 不增加Phase
- 主线成型后（>=3只）批量重新计算
- 修改 `_update_mainlines()` 即可

**实施耗时**：约1.5小时

**确认后我立即实施。**
