# 股票上攻排行新增涨跌幅字段设计方案

> 设计时间: 2026-03-31 01:12  
> 目标: 新增涨跌幅字段，通过Redis获取实时数据，不影响现有业务

---

## 需求分析

### 需求要点
| 项目 | 说明 |
|------|------|
| **字段位置** | 名称后面，次数前面 |
| **字段名称** | 涨跌幅 (change_pct) |
| **数据来源** | Redis - `monitor_gp_top30_20260330:{time}` |
| **数据字段** | `change_pct_now` |
| **兼容性** | 不影响现有业务 |

### 显示顺序
```
当前: # | 代码 | 名称 | 次数 | 债券代码 | 债券名称 | 行业
新增: # | 代码 | 名称 | 涨跌幅 | 次数 | 债券代码 | 债券名称 | 行业
```

---

## 数据流分析

### 当前数据流
```
GET /api/monitor/attack-ranking/stock
  ↓
get_stock_ranking() [monitor.py]
  ↓
data_service.get_stock_ranking() / get_ranking_at_time()
  ↓
_process_stock_ranking() [添加债券/行业/红名单]
  ↓
返回: [{code, name, count, bond_code, bond_name, industry_name, is_red}]
```

### 新增数据流
```
GET /api/monitor/attack-ranking/stock
  ↓
get_stock_ranking() [monitor.py]
  ↓
data_service.get_stock_ranking() / get_ranking_at_time()
  ↓
_process_stock_ranking() [添加债券/行业/红名单]
  ↓
_enrich_change_pct() [新增：从Redis获取涨跌幅]
  ↓
返回: [{code, name, change_pct, count, bond_code, bond_name, industry_name, is_red}]
```

---

## 技术方案

### 方案A: 实时查询Redis（推荐）

在 `_process_stock_ranking` 中增加涨跌幅查询：

```python
def _enrich_change_pct(self, stocks: list, date: str, time_str: str = None) -> list:
    """
    为股票数据添加涨跌幅
    
    从Redis的monitor_gp_top30表获取指定时间的change_pct_now
    """
    if not stocks:
        return stocks
    
    try:
        from gs2026.utils import redis_util
        client = redis_util._get_redis_client()
        
        # 构建表名
        table_name = f"monitor_gp_top30_{date}"
        
        # 确定查询时间
        if time_str:
            # 时间轴回放模式 - 使用指定时间
            query_time = time_str
        else:
            # 实时模式 - 获取最新时间
            ts_key = f"{table_name}:timestamps"
            latest_ts = client.lindex(ts_key, 0)  # 获取最新时间戳
            if latest_ts:
                query_time = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
            else:
                # 无时间戳数据，返回原数据
                for stock in stocks:
                    stock['change_pct'] = None
                return stocks
        
        # 从Redis获取该时间点的DataFrame
        redis_key = f"{table_name}:{query_time}"
        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
        
        if df is None or df.empty:
            # Redis无数据，返回原数据
            for stock in stocks:
                stock['change_pct'] = None
            return stocks
        
        # 构建code -> change_pct映射
        change_pct_map = {}
        for _, row in df.iterrows():
            code = str(row.get('code', '')).zfill(6)
            change_pct = row.get('change_pct_now') or row.get('change_pct')
            if code and change_pct is not None:
                change_pct_map[code] = float(change_pct)
        
        # 为每只股票添加涨跌幅
        for stock in stocks:
            code = stock.get('code', '').zfill(6)
            stock['change_pct'] = change_pct_map.get(code)
        
        return stocks
        
    except Exception as e:
        print(f"获取涨跌幅失败: {e}")
        # 出错时返回原数据，change_pct为null
        for stock in stocks:
            stock['change_pct'] = None
        return stocks
```

### 方案B: Pipeline批量优化（高性能）

如果方案A性能不够，使用Pipeline批量获取：

```python
def _enrich_change_pct_optimized(self, stocks: list, date: str, time_str: str = None) -> list:
    """优化版：使用Pipeline批量获取涨跌幅"""
    if not stocks:
        return stocks
    
    try:
        from gs2026.utils import redis_util
        client = redis_util._get_redis_client()
        
        table_name = f"monitor_gp_top30_{date}"
        
        # 获取查询时间
        if time_str:
            query_time = time_str
        else:
            ts_key = f"{table_name}:timestamps"
            latest_ts = client.lindex(ts_key, 0)
            if not latest_ts:
                for stock in stocks:
                    stock['change_pct'] = None
                return stocks
            query_time = latest_ts.decode('utf-8') if isinstance(latest_ts, bytes) else latest_ts
        
        # 获取DataFrame
        redis_key = f"{table_name}:{query_time}"
        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
        
        if df is None or df.empty:
            for stock in stocks:
                stock['change_pct'] = None
            return stocks
        
        # 使用向量化操作（比循环快）
        # 创建code -> change_pct的Series
        df['code'] = df['code'].astype(str).str.zfill(6)
        change_pct_series = df.set_index('code')['change_pct_now']
        
        # 批量映射
        for stock in stocks:
            code = stock.get('code', '').zfill(6)
            stock['change_pct'] = change_pct_series.get(code)
        
        return stocks
        
    except Exception as e:
        print(f"获取涨跌幅失败: {e}")
        for stock in stocks:
            stock['change_pct'] = None
        return stocks
```

---

## 修改点

### 1. 后端修改 - monitor.py

```python
# 在 _process_stock_ranking 方法中添加涨跌幅查询

def _process_stock_ranking(self, data: list, date: str = None, time_str: str = None) -> list:
    """
    统一处理股票排行数据：
    - 补充债券/行业信息
    - 标记红名单
    - 添加涨跌幅 [新增]
    - 红名单优先排序
    """
    if not data:
        return data
    
    # 补充债券和行业信息
    data = _enrich_stock_data(data)
    
    # 添加涨跌幅 [新增]
    data = self._enrich_change_pct(data, date or datetime.now().strftime('%Y%m%d'), time_str)
    
    # 标记红名单
    try:
        from gs2026.dashboard2.routes.red_list_cache import get_red_list
        red_list = get_red_list()
        for item in data:
            item['is_red'] = item.get('code', '') in red_list
    except Exception:
        for item in data:
            item['is_red'] = False
    
    # 排序：红名单优先，然后按次数倒序
    data.sort(key=lambda x: (-int(x.get('is_red', False)), -x.get('count', 0)))
    
    return data


# 新增方法：获取涨跌幅
def _enrich_change_pct(self, stocks: list, date: str, time_str: str = None) -> list:
    """为股票数据添加涨跌幅"""
    # ... 实现代码见上方 ...
    pass
```

### 2. 前端修改 - monitor.html

```html
<!-- 修改表格表头 -->
<thead>
    <tr>
        <th>#</th>
        <th>代码</th>
        <th>名称</th>
        <th>涨跌幅</th>  <!-- 新增 -->
        <th>次数</th>
        <th>债券代码</th>
        <th>债券名称</th>
        <th>行业</th>
    </tr>
</thead>

<!-- 修改表格行渲染 -->
<tbody id="ranking-body">
    <!-- JavaScript动态生成 -->
</tbody>

<script>
function renderStockRanking(data) {
    const tbody = document.getElementById('ranking-body');
    
    const html = data.map((item, index) => {
        // 涨跌幅样式：正数红色，负数绿色，null灰色
        let changePctClass = 'text-gray';
        let changePctText = '-';
        if (item.change_pct !== null && item.change_pct !== undefined) {
            const pct = parseFloat(item.change_pct);
            if (pct > 0) {
                changePctClass = 'text-red';
                changePctText = `+${pct.toFixed(2)}%`;
            } else if (pct < 0) {
                changePctClass = 'text-green';
                changePctText = `${pct.toFixed(2)}%`;
            } else {
                changePctText = '0.00%';
            }
        }
        
        // 红名单样式
        const rowClass = item.is_red ? 'red-list-row' : '';
        const redBadge = item.is_red ? '<span class="red-badge">红</span>' : '';
        
        return `
            <tr class="${rowClass}">
                <td>${index + 1}</td>
                <td>${item.code}</td>
                <td>${item.name}${redBadge}</td>
                <td class="${changePctClass}">${changePctText}</td>  <!-- 新增 -->
                <td>${item.count}</td>
                <td>${item.bond_code || '-'}</td>
                <td>${item.bond_name || '-'}</td>
                <td>${item.industry_name || '-'}</td>
            </tr>
        `;
    }).join('');
    
    tbody.innerHTML = html;
}
</script>

<style>
/* 涨跌幅颜色样式 */
.text-red { color: #ff4d4f; font-weight: 600; }
.text-green { color: #52c41a; font-weight: 600; }
.text-gray { color: #999; }

/* 红名单行样式 */
.red-list-row {
    background-color: rgba(255, 77, 79, 0.05);
}

/* 红名单标记 */
.red-badge {
    display: inline-block;
    background: #ff4d4f;
    color: white;
    font-size: 10px;
    padding: 1px 4px;
    border-radius: 3px;
    margin-left: 4px;
}
</style>
```

---

## 数据兼容性处理

### 情况1: Redis有数据
- 正常返回涨跌幅

### 情况2: Redis无数据
- `change_pct` 设为 `null`
- 前端显示 `-`

### 情况3: 查询异常
- 捕获异常，不影响其他字段
- `change_pct` 设为 `null`

### 情况4: 字段不存在
- 尝试 `change_pct_now` 字段
- 不存在则尝试 `change_pct`
- 都不存在则设为 `null`

---

## API响应格式

```json
{
    "success": true,
    "data": [
        {
            "code": "000001",
            "name": "平安银行",
            "change_pct": 2.35,        // 新增字段
            "count": 15,
            "bond_code": "113042",
            "bond_name": "平安转债",
            "industry_name": "银行",
            "is_red": true
        },
        {
            "code": "000002",
            "name": "万科A",
            "change_pct": -1.20,       // 负数表示下跌
            "count": 12,
            "bond_code": "-",
            "bond_name": "-",
            "industry_name": "房地产",
            "is_red": false
        },
        {
            "code": "000063",
            "name": "中兴通讯",
            "change_pct": null,        // 无数据时null
            "count": 8,
            "bond_code": "-",
            "bond_name": "-",
            "industry_name": "通信设备",
            "is_red": false
        }
    ],
    "count": 60,
    "type": "stock"
}
```

---

## 实施计划

### 阶段1: 后端实现（30分钟）
- [ ] 在 `monitor.py` 中添加 `_enrich_change_pct` 方法
- [ ] 修改 `_process_stock_ranking` 调用新方法
- [ ] 测试API返回格式

### 阶段2: 前端实现（30分钟）
- [ ] 修改 `monitor.html` 表头
- [ ] 修改 `renderStockRanking` 函数
- [ ] 添加涨跌幅样式

### 阶段3: 测试验证（15分钟）
- [ ] 测试Redis有数据的情况
- [ ] 测试Redis无数据的情况
- [ ] 测试时间轴回放模式
- [ ] 确认不影响现有功能

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Redis查询慢 | 低 | 中 | 使用缓存或优化查询 |
| 字段不存在 | 低 | 低 | 多字段fallback |
| 影响现有排序 | 低 | 中 | 保持原有排序逻辑 |

---

## 备选方案

如果实时查询Redis性能不佳：

**方案B: 内存缓存**
- 5秒缓存涨跌幅数据
- 减少Redis查询次数

**方案C: 预加载**
- 后台定时预加载到内存
- 查询时直接返回

---

**文档位置**: `docs/stock_ranking_change_pct_design.md`

**请确认方案后实施。**
