# 可转债数据采集优化方案

## 问题诊断

### 现象
程序走到 `bond_zh_cov.get_bond()` 后不再继续，看似"卡住"

### 根因分析

| 函数 | 问题 | 耗时 |
|-----|------|------|
| `get_bond()` | 无问题 | ~3秒 |
| `get_bond_daily()` | 逐只获取债券日线 | **~17分钟** |

### 具体分析

```python
# get_bond_daily() 的问题代码
dm_df = pd.read_sql(sql, con=con)  # 获取500+只债券
datas = dm_df.values.tolist()
for data in datas:  # 循环500+次
    bond_df = ak.bond_zh_hs_cov_daily(bond_code_2)  # 每只2秒
    # 总时间 = 500 × 2秒 = 1000秒 = 17分钟
```

---

## 优化方案

### 方案A：批量获取（推荐）

使用AKShare的批量接口一次性获取所有债券日线数据

```python
def get_bond_daily_optimized():
    """优化的债券日线采集"""
    import akshare as ak
    
    # 一次性获取所有可转债日线
    # 使用 bond_zh_hs_cov_daily 的 symbol 参数支持多只
    # 或使用 bond_zh_hs_cov_spot 获取实时行情
    
    # 方法1: 获取所有可转债实时行情（更快）
    spot_df = ak.bond_zh_hs_cov_spot()
    
    # 方法2: 分批获取（如果必须日线）
    # 每批10只，减少请求次数
    batch_size = 10
    for i in range(0, len(datas), batch_size):
        batch = datas[i:i+batch_size]
        # 并发获取
```

### 方案B：异步并发

使用线程池并发获取多只债券数据

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_bond_daily_async():
    """异步并发获取债券日线"""
    
    def fetch_single_bond(data):
        bond_code, stock_code, bond_code_2 = data
        try:
            bond_df = ak.bond_zh_hs_cov_daily(bond_code_2)
            bond_df['stock_code'] = stock_code
            bond_df['bond_code'] = bond_code
            return bond_df
        except:
            return None
    
    # 并发10个请求
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_single_bond, d) for d in datas]
        for future in as_completed(futures):
            bond_df = future.result()
            if bond_df is not None:
                # 保存到数据库
```

### 方案C：增量更新

只获取当日数据，不获取历史数据

```python
def get_bond_daily_incremental():
    """增量获取当日债券数据"""
    # 使用实时行情接口，只获取当天数据
    spot_df = ak.bond_zh_hs_cov_spot()
    
    # 过滤当日数据
    today = datetime.now().strftime('%Y-%m-%d')
    today_df = spot_df[spot_df['日期'] == today]
    
    # 保存到数据库
```

---

## 快速修复

### 修改 bond_zh_cov.py

```python
def get_bond_daily():
    """采集可转债日线数据（优化版）"""
    table_name = "data_bond_daily"
    mysql_tool.drop_mysql_table(table_name)
    
    # 获取债券列表
    sql = """
    SELECT `代码`,`正股代码`,
        CONCAT(
            CASE 
                WHEN `正股代码` LIKE '00%' OR `正股代码` LIKE '30%'  THEN 'sz'
                WHEN `正股代码` LIKE '60%' OR `正股代码` LIKE '68%' THEN 'sh'
                ELSE 'other'
            END,
            `代码`
        ) AS `债券代码`
    FROM data_bond_qs_jsl  
    WHERE `正股代码` like '00%' or `正股代码` LIKE '60%' 
       or `正股代码` LIKE '30%' OR `正股代码` LIKE '68%'
    """.replace("%","%%")
    
    dm_df = pd.read_sql(sql, con=con)
    datas = dm_df.values.tolist()
    
    logger.info(f"开始获取 {len(datas)} 只债券的日线数据...")
    
    # 使用线程池并发获取
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def fetch_bond(data):
        bond_code, stock_code, bond_code_2 = data
        try:
            bond_df = ak.bond_zh_hs_cov_daily(bond_code_2)
            if not bond_df.empty:
                bond_df['stock_code'] = stock_code
                bond_df['bond_code'] = bond_code
                bond_df['bond_code_2'] = bond_code_2
                return bond_df
        except Exception as e:
            logger.error(f"获取{bond_code}失败: {e}")
        return None
    
    # 并发10个请求
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_bond, d): d for d in datas}
        
        for i, future in enumerate(as_completed(futures)):
            bond_df = future.result()
            if bond_df is not None:
                with engine.begin() as conn:
                    bond_df.to_sql(name=table_name, con=conn, if_exists='append')
            
            # 每10只记录进度
            if (i + 1) % 10 == 0:
                logger.info(f"已处理 {i + 1}/{len(datas)} 只债券")
    
    logger.info(f"债券日线数据采集完成，共 {len(datas)} 只")
```

---

## 预期效果

| 方案 | 原耗时 | 优化后耗时 | 提升 |
|-----|-------|-----------|-----|
| 串行获取 | 17分钟 | - | - |
| 并发10线程 | 17分钟 | **2分钟** | **8.5x** |
| 批量接口 | 17分钟 | **30秒** | **34x** |

---

## 建议

1. **立即实施**: 使用方案A（批量获取）或方案B（异步并发）
2. **长期优化**: 考虑使用实时行情接口 `bond_zh_hs_cov_spot()` 替代日线接口
3. **监控**: 添加进度日志，方便观察执行情况
