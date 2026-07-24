# 300992 债券关联问题排查方案

> 排查时间: 2026-03-31 11:37  
> 目标: 排查 get_stock_bond_industry_mapping 中 300992 没有关联债券的原因

---

## 一、代码逻辑分析

### 1.1 数据关联流程

```python
# 步骤1: 查询行业成分股表
industry_df = SELECT stock_code, short_name, code, name FROM data_industry_code_component_ths

# 步骤2: 查询债券最新价格（带价格过滤）
price_df = SELECT bond_code, close, date FROM data_bond_daily
            WHERE date = '最新日期'
            AND close >= 120.0    ← 价格下限
            AND close <= 250.0    ← 价格上限

# 步骤3: 查询债券基础信息
bond_df = SELECT 债券代码, 债券简称, 正股代码 FROM data_bond_ths
            WHERE 上市日期 <= 今天
            AND 申购日期 < DATE_SUB(今天, INTERVAL 30 DAY)

# 步骤4: 关联债券信息和价格（INNER JOIN）
bond_with_price = bond_df INNER JOIN price_df ON bond_code

# 步骤5: 以股票为主关联（LEFT JOIN）
merged_df = industry_df LEFT JOIN bond_with_price ON stock_code
```

### 1.2 关键过滤条件

| 步骤 | 过滤条件 | 影响 |
|------|----------|------|
| price_df | close >= 120 AND close <= 250 | **最可能原因** |
| bond_df | 上市日期 <= 今天 | 排除未上市债券 |
| bond_df | 申购日期 < 今天-30天 | 排除临近赎回债券 |
| merge | INNER JOIN price_df | 无价格信息则被过滤 |

---

## 二、排查步骤

### 步骤1: 检查123160债券当前价格

```sql
-- 查询123160的最新价格
SELECT bond_code, close, date 
FROM data_bond_daily 
WHERE bond_code = '123160' 
ORDER BY date DESC 
LIMIT 5;
```

**可能结果**:
- 如果 close < 120 或 close > 250 → **价格过滤导致**
- 如果没有记录 → 日行情表无数据

### 步骤2: 检查债券基础信息

```sql
-- 查询123160的基础信息
SELECT 
    `债券代码`, 
    `债券简称`, 
    `正股代码`, 
    `上市日期`, 
    `申购日期`
FROM data_bond_ths 
WHERE `债券代码` = '123160';
```

**可能结果**:
- 如果 正股代码 != '300992' → 数据错误
- 如果 上市日期 > 今天 → 未上市
- 如果 申购日期 >= 今天-30天 → 临近赎回被过滤

### 步骤3: 检查300992是否在行业成分股表

```sql
-- 查询300992是否在行业表
SELECT stock_code, short_name, code, name 
FROM data_industry_code_component_ths 
WHERE stock_code = '300992';
```

**可能结果**:
- 如果没有记录 → 行业表无此股票

### 步骤4: 完整关联查询验证

```sql
-- 模拟完整的关联查询，查看123160在哪个环节丢失
WITH price_data AS (
    SELECT bond_code, close, date 
    FROM data_bond_daily 
    WHERE date = (SELECT MAX(date) FROM data_bond_daily)
),
bond_data AS (
    SELECT 
        `债券代码` AS bond_code,
        `债券简称` AS bond_name,
        `正股代码` AS stock_code
    FROM data_bond_ths
    WHERE `债券代码` = '123160'
)
SELECT 
    b.*,
    p.close as bond_price,
    CASE 
        WHEN p.close IS NULL THEN '无价格数据'
        WHEN p.close < 120 THEN '价格低于120'
        WHEN p.close > 250 THEN '价格高于250'
        ELSE '价格正常'
    END as price_status
FROM bond_data b
LEFT JOIN price_data p ON b.bond_code = p.bond_code;
```

---

## 三、可能原因及解决方案

### 原因1: 债券价格超出范围（最可能）

**判断**: 123160当前价格 < 120 或 > 250

**验证**:
```sql
SELECT close FROM data_bond_daily WHERE bond_code = '123160' ORDER BY date DESC LIMIT 1;
-- 如果结果 < 120 或 > 250，确认此原因
```

**解决方案A**: 调整价格过滤参数
```python
# 修改 stock_bond_mapping_cache.py 中的 update_mapping 调用
mapping_df = get_stock_bond_industry_mapping(
    min_bond_price=0.0,      # 改为0，不排除低价债券
    max_bond_price=1000.0,   # 放宽到1000
    redemption_days_threshold=30
)
```

**解决方案B**: 移除价格过滤（如果业务不需要）
```python
# 修改 stock_bond_industry_mapping.py
# 删除价格过滤条件
latest_price_query = f"""
    SELECT 
        bond_code,
        close as bond_price,
        date as price_date
    FROM {bond_daily_table}
    WHERE date = '{latest_date}'
    -- 删除: AND close >= {min_bond_price}
    -- 删除: AND close <= {max_bond_price}
"""
```

---

### 原因2: 债券临近赎回日期

**判断**: 申购日期距离今天 <= 30天

**验证**:
```sql
SELECT 
    `债券代码`,
    `申购日期`,
    DATEDIFF(NOW(), `申购日期`) as days_since_apply
FROM data_bond_ths 
WHERE `债券代码` = '123160';
-- 如果 days_since_apply <= 30，确认此原因
```

**解决方案**: 调整赎回阈值或移除此过滤
```python
mapping_df = get_stock_bond_industry_mapping(
    redemption_days_threshold=0,  # 改为0，不排除临近赎回债券
)
```

---

### 原因3: 债券未上市

**判断**: 上市日期 > 今天

**验证**:
```sql
SELECT `上市日期` FROM data_bond_ths WHERE `债券代码` = '123160';
-- 如果 上市日期 > CURDATE()，确认此原因
```

**解决方案**: 检查数据准确性，或移除上市日期过滤

---

### 原因4: 日行情表无数据

**判断**: data_bond_daily 表中没有123160的记录

**验证**:
```sql
SELECT COUNT(*) FROM data_bond_daily WHERE bond_code = '123160';
-- 如果结果为0，确认此原因
```

**解决方案**: 检查日行情数据采集是否正常

---

### 原因5: 正股代码不匹配

**判断**: data_bond_ths 中的正股代码不是300992

**验证**:
```sql
SELECT `正股代码` FROM data_bond_ths WHERE `债券代码` = '123160';
-- 如果结果 != '300992'，确认此原因
```

**解决方案**: 检查债券基础数据准确性

---

## 四、快速排查脚本

```python
# 保存为 debug_bond_mapping.py 执行
import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config("common.url")
engine = create_engine(url)

with engine.connect() as conn:
    print("=" * 60)
    print("排查 300992 - 123160 债券关联问题")
    print("=" * 60)
    
    # 1. 检查行业表
    result = conn.execute(text("""
        SELECT stock_code, short_name 
        FROM data_industry_code_component_ths 
        WHERE stock_code = '300992'
    """)).fetchone()
    print(f"\n1. 行业成分股表: {result if result else '无记录'}")
    
    # 2. 检查债券基础信息
    result = conn.execute(text("""
        SELECT `债券代码`, `债券简称`, `正股代码`, `上市日期`, `申购日期`
        FROM data_bond_ths 
        WHERE `债券代码` = '123160'
    """)).fetchone()
    print(f"\n2. 债券基础信息: {result if result else '无记录'}")
    
    # 3. 检查债券价格
    result = conn.execute(text("""
        SELECT bond_code, close, date 
        FROM data_bond_daily 
        WHERE bond_code = '123160'
        ORDER BY date DESC 
        LIMIT 1
    """)).fetchone()
    print(f"\n3. 债券最新价格: {result if result else '无记录'}")
    if result:
        close_price = result[1]
        if close_price < 120:
            print(f"   ⚠️ 价格 {close_price} 低于下限 120，被过滤！")
        elif close_price > 250:
            print(f"   ⚠️ 价格 {close_price} 高于上限 250，被过滤！")
        else:
            print(f"   ✓ 价格 {close_price} 在正常范围")
    
    # 4. 检查完整关联
    result = conn.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT b.`债券代码`, b.`正股代码`, p.close
            FROM data_bond_ths b
            JOIN data_bond_daily p ON b.`债券代码` = p.bond_code
            WHERE b.`债券代码` = '123160'
            AND p.date = (SELECT MAX(date) FROM data_bond_daily)
            AND p.close >= 120 AND p.close <= 250
        ) t
    """)).fetchone()
    print(f"\n4. 关联后记录数: {result[0]} {'✓ 存在' if result[0] > 0 else '⚠️ 被过滤'}")

print("\n" + "=" * 60)
print("排查完成")
print("=" * 60)
```

---

## 五、推荐解决方案

### 方案A: 放宽价格限制（推荐）

**原因**: 123160可能是低价债券（<120）或高价债券（>250）

**实施**:
```python
# 修改 stock_bond_mapping_cache.py
result = cache.update_mapping(
    min_bond_price=0.0,      # 不设下限
    max_bond_price=500.0,    # 放宽上限
    force=True
)
```

### 方案B: 显示所有债券（不移除价格过滤但显示）

修改映射逻辑，价格过滤只影响排序/推荐，不影响显示:
```python
# 修改 stock_bond_industry_mapping.py
# 先获取所有债券，再标记是否在价格范围内
def get_stock_bond_industry_mapping(...):
    # ... 获取所有债券（不过滤价格）
    # 添加一列标记是否在价格范围内
    merged_df['in_price_range'] = merged_df['bond_price'].apply(
        lambda x: min_bond_price <= x <= max_bond_price if pd.notna(x) else False
    )
    return merged_df
```

### 方案C: 检查并修正数据源

如果123160确实不应该被过滤，检查:
1. data_bond_daily 表数据是否正确
2. data_bond_ths 表数据是否正确

---

**请先执行快速排查脚本，确定具体原因后再实施解决方案。**
