# Phase2优化方案（关联分析+批量更新role）

## 用户核心诉求澄清

**当前理解**：
- Phase 2 是"关联主线分析"步骤
- 优化后，这个步骤应该**同时做两件事**：
  1. 关联主线分析（原有功能）
  2. 重新将该股票所属主线的**所有股票role更新**（新增功能）

**关键问题**：
- 是否需要在Phase 2中**重新计算该主线所有股票的role**？
- 还是只**更新当前股票的role**？

---

## 当前Phase 2流程分析

```python
def analyze_correlation(engine, anomaly, ...):
    """
    当前Phase 2：关联主线分析
    """
    # 1. 获取当日所有涨停
    all_zt = _get_today_all_zt(engine, trading_date, anomaly_id)
    
    # 2. 获取已识别主线
    existing_mainlines = _get_existing_mainlines(engine, trading_date)
    
    # 3. 构建Prompt
    prompt = build_correlation_prompt(anomaly, all_zt, existing_mainlines, ...)
    
    # 4. AI分析
    response = _call_ai(prompt)
    
    # 5. 解析结果
    mainline_results = analysis.get('主线归属', [])
    
    # 6. 更新主线和关系表
    # 【当前】只更新当前股票的role
    _update_mainlines(engine, anomaly_id, trading_date, anomaly_data, mainline_results)
```

**当前 `_update_mainlines` 的问题**：
- 只更新**当前股票**的role
- 不更新**同主线其他股票**的role
- 导致：主线成型后，早期股票role错误

---

## 优化方案：Phase 2 同时做两件事

### 方案A：Phase 2 中批量更新该主线所有role（推荐）

**核心思路**：
```
Phase 2（关联主线分析）
    ↓
1. 获取当日所有涨停
2. 获取已识别主线
3. AI分析（当前股票的主线归属 + role）
    ↓
4. 【新增】获取该主线所有股票
5. 【新增】基于当前完整信息，重新计算该主线所有股票的role
6. 【新增】批量更新该主线所有股票的role
```

**实现**：

```python
def analyze_correlation_v2(engine, anomaly, bk_dic_str, gn_dic_str, redis_client):
    """
    改进版Phase 2：关联分析 + 批量更新该主线所有role
    """
    anomaly_id = anomaly['id']
    trading_date = str(anomaly['trading_date'])
    
    # ========== 原有功能：关联主线分析 ==========
    
    # 1. 获取当日所有涨停
    all_zt = _get_today_all_zt(engine, trading_date, anomaly_id)
    
    # 2. 获取已识别主线
    existing_mainlines = _get_existing_mainlines(engine, trading_date)
    
    # 3. 构建Prompt
    prompt = build_correlation_prompt(anomaly, all_zt, existing_mainlines, 
                                     bk_dic_str, gn_dic_str)
    
    # 4. AI分析
    response = _call_ai(prompt)
    
    # 5. 解析结果
    from gs2026.utils.string_util import clean_ai_response
    import re
    response = clean_ai_response(response)
    response = re.sub(r'<think>[\s\S]*?</think>', '', response).strip()
    
    try:
        analysis = json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            raise
    
    mainline_results = analysis.get('主线归属', [])
    
    # 6. 更新主线和当前股票role
    _update_mainlines(engine, anomaly_id, trading_date, anomaly, mainline_results)
    
    # ========== 新增功能：批量更新该主线所有role ==========
    
    for ml in mainline_results:
        if ml.get('type') == 'independent':
            continue
        
        mainline_name = ml.get('mainline_name', '')
        
        # 【关键】获取该主线所有股票（包括当前股票）
        mainline_stocks = get_mainline_all_stocks(engine, mainline_name, trading_date)
        
        if len(mainline_stocks) < 2:
            # 只有1只，跳过
            continue
        
        logger.info(f"[Phase2优化] 主线 {mainline_name} 有 {len(mainline_stocks)} 只股票，"
                   f"重新计算所有role...")
        
        # 【关键】基于当前完整信息，重新计算所有role
        # 方案A1：基于规则（无AI调用）
        updated_roles = recalculate_roles_by_rule(mainline_stocks)
        
        # 方案A2：轻量级AI（如果需要更精准）
        # updated_roles = recalculate_roles_by_light_ai(mainline_stocks)
        
        # 【关键】批量更新所有股票的role
        batch_update_roles(engine, updated_roles, trading_date)
        
        logger.info(f"[Phase2优化] 主线 {mainline_name} role更新完成")
    
    return True
```

### 方案B：只更新当前股票role（不推荐）

**问题**：
- 只更新当前股票，不更新同主线其他股票
- 早期股票role仍然错误
- 不符合用户"重新将所有该股票下的主线的所有股票重新更新role"的要求

---

## 关键实现细节

### 1. 获取主线所有股票

```python
def get_mainline_all_stocks(engine, mainline_name: str, trading_date: str) -> list:
    """
    获取指定主线的所有股票
    """
    import hashlib
    mainline_id = hashlib.md5(f"{mainline_name}_{trading_date}".encode()).hexdigest()
    
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
                r.evidence,
                r.confidence_contribution
            FROM stock_anomaly_mainline_rel r
            JOIN stock_anomaly a ON r.anomaly_id = a.id
            JOIN stock_anomaly_mainline m ON r.mainline_id = m.mainline_id
            WHERE m.mainline_name = :mainline_name
              AND a.trading_date = :date
            ORDER BY a.anomaly_time ASC
        """), {'mainline_name': mainline_name, 'date': trading_date})
        
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]
```

### 2. 基于规则重新计算role

```python
def recalculate_roles_by_rule(stocks: list) -> list:
    """
    基于规则重新计算role（无AI调用）
    
    规则：
    1. 主线内第1只涨停 → 龙头（如果逻辑正宗）
    2. 第2-3只涨停 → 补涨
    3. 第4只以后 → 跟风
    4. 连板数高的可提升role
    """
    # 按时间排序
    sorted_stocks = sorted(stocks, key=lambda x: x['anomaly_time'])
    
    result = []
    
    for i, stock in enumerate(sorted_stocks):
        # 基础role分配
        if i == 0:
            base_role = '龙头'
        elif i <= 2:
            base_role = '补涨'
        else:
            base_role = '跟风'
        
        # 连板数修正
        continuous_zt = stock.get('continuous_zt', 0)
        if continuous_zt >= 2 and base_role == '跟风':
            # 2连板以上，从跟风提升为补涨
            base_role = '补涨'
        
        # 评分计算
        score = calculate_score(i, continuous_zt)
        
        result.append({
            'anomaly_id': stock['anomaly_id'],
            'stock_code': stock['stock_code'],
            'stock_name': stock['stock_name'],
            'old_role': stock.get('role'),
            'new_role': base_role,
            'score': score,
            'reason': f'主线内第{i+1}只涨停，{continuous_zt}连板'
        })
    
    return result


def calculate_score(rank: int, continuous_zt: int) -> int:
    """计算龙头强度评分"""
    # 基础分
    base_score = max(100 - rank * 15, 20)  # 第1只100分，第2只85分...
    
    # 连板加分
    zt_bonus = continuous_zt * 10  # 每连板+10分
    
    return min(base_score + zt_bonus, 100)
```

### 3. 批量更新role

```python
def batch_update_roles(engine, updated_roles: list, trading_date: str):
    """
    批量更新股票的role
    """
    import hashlib
    
    with engine.connect() as conn:
        for role_info in updated_roles:
            # 获取mainline_id
            result = conn.execute(text("""
                SELECT mainline_id FROM stock_anomaly_mainline_rel
                WHERE anomaly_id = :aid
                LIMIT 1
            """), {'aid': role_info['anomaly_id']})
            row = result.fetchone()
            if not row:
                continue
            mainline_id = row[0]
            
            # 更新role
            conn.execute(text("""
                UPDATE stock_anomaly_mainline_rel
                SET role = :role,
                    confidence_contribution = :score
                WHERE anomaly_id = :aid AND mainline_id = :mid
            """), {
                'aid': role_info['anomaly_id'],
                'mid': mainline_id,
                'role': role_info['new_role'],
                'score': role_info['score']
            })
        
        conn.commit()
```

---

## 方案对比

| 维度 | 方案A（批量更新） | 方案B（只更新当前） |
|------|------------------|-------------------|
| **符合用户要求** | ⭐⭐⭐ 是 | ⭐ 否 |
| **数据一致性** | ⭐⭐⭐ 高 | ⭐⭐ 中 |
| **实现复杂度** | ⭐⭐ 中 | ⭐ 低 |
| **性能影响** | ⭐⭐ 中（批量更新） | ⭐⭐⭐ 低 |
| **推荐度** | ⭐⭐⭐ **推荐** | ⭐⭐ 不推荐 |

---

## 推荐方案：方案A（Phase 2 批量更新）

### 核心流程

```
analyze_correlation_v2() 改进版
    ↓
1. 关联主线分析（原有功能）
   - 获取当日所有涨停
   - 获取已识别主线
   - AI分析
   - 更新当前股票role
    ↓
2. 【新增】批量更新该主线所有role
   - 获取该主线所有股票
   - 基于规则重新计算role（无AI调用）
   - 批量更新所有股票的role
```

### 实施步骤（约1.5小时）

| 步骤 | 耗时 |
|------|------|
| 修改 `analyze_correlation()` → `analyze_correlation_v2()` | 30分钟 |
| 新增 `get_mainline_all_stocks()` | 10分钟 |
| 新增 `recalculate_roles_by_rule()` | 20分钟 |
| 新增 `batch_update_roles()` | 15分钟 |
| 测试验证 | 15分钟 |
| **总计** | **约1.5小时** |

### 预期效果

- **AI应用主线32只股票**：
  - 第1只分析时：主线只有1只，role=龙头
  - 第3只分析时：主线成型，**重新计算前3只的role**
  - 第32只分析时：主线完整，**重新计算所有32只的role**
  
- **最终结果**：
  - 1-2只真龙头（评分>80）
  - 3-5只补涨（评分60-80）
  - 其余跟风（评分<60）

---

## 结论

**方案可行！**

**推荐方案A**：
- Phase 2 同时做两件事：
  1. 关联主线分析（原有）
  2. 批量更新该主线所有role（新增）
- 基于规则重新计算（无AI调用）
- 数据一致性高，符合用户要求

**确认后我立即实施。**
