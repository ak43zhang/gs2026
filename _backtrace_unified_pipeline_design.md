# 股债交集回溯系统 - 统一过滤管道设计方案

## 核心原则

**单一维护点**: 过滤管道逻辑只在后端维护一套，前后端不重复实现。

## 当前问题

- 前端有一套 Pipeline 实现（JavaScript）
- 后端需要再实现一套（Python）
- 同一逻辑维护两套，容易不一致

## 解决方案

### 方案：后端主导的统一过滤服务

**架构调整**:

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (UI)                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 过滤配置面板                                          │ │
│  │ - 只负责收集用户选择的过滤条件                         │ │
│  │ - 不执行任何过滤逻辑                                  │ │
│  │ - 将配置发送到后端 API                                │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │ 过滤配置 JSON
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      后端 (唯一维护点)                       │
│                    ┌──────────────────┐                     │
│                    │  UnifiedPipeline │                     │
│                    │  (统一过滤管道)   │                     │
│                    └──────────────────┘                     │
│                           │                                 │
│         ┌─────────────────┼─────────────────┐              │
│         ▼                 ▼                 ▼              │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐     │
│  │ 实时查询    │   │ 回溯任务    │   │ 测试验证    │     │
│  │ /filter    │   │ /backtrace │   │ /validate  │     │
│  └─────────────┘   └─────────────┘   └─────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

**关键变化**:

1. **前端不再执行过滤逻辑**
   - 前端只收集过滤配置
   - 通过 API 发送到后端
   - 后端返回过滤后的数据

2. **后端统一实现过滤管道**
   - 实时查询：股票/债券排行 API 调用统一 Pipeline
   - 回溯任务：直接复用同一套 Pipeline
   - 测试验证：验证过滤配置有效性

3. **过滤配置标准化**
   - 前后端共享同一套配置 Schema
   - JSON 格式传输
   - 版本控制保证兼容性

## 详细设计

### 1. 过滤配置 Schema

```typescript
// 前后端共享的配置类型定义
interface FilterConfig {
  version: "1.0";
  stock: StockFilterConfig;
  bond: BondFilterConfig;
}

interface StockFilterConfig {
  industry?: string;           // 行业筛选
  topn_sectors?: number;     // 仅前N行业（次数）
  topn_sectors_pct?: number;   // 仅前N行业（涨幅）
  topn_window?: number;      // 仅前N区间次数
  topn_count?: number;       // 仅前N累计次数
  bond_filter?: boolean;     // 仅显示有债券的
}

interface BondFilterConfig {
  industry?: string;           // 行业筛选
  topn_sectors?: number;       // 仅前N行业（次数）
  topn_sectors_pct?: number;   // 仅前N行业（涨幅）
  topn_amount?: number;        // 仅前N金额
  topn_window?: number;        // 仅前N区间次数
  topn_count?: number;         // 仅前N累计次数
  green_list?: boolean;        // 排除绿名单
}
```

### 2. 后端统一 Pipeline

```python
# src/gs2026/common/pipeline.py
# 统一过滤管道 - 唯一维护点

class UnifiedPipeline:
    """
    统一过滤管道
    
    所有过滤逻辑只在此实现，前后端共用。
    """
    
    def __init__(self, config: FilterConfig):
        self.config = config
        self.stock_pipeline = self._build_stock_pipeline()
        self.bond_pipeline = self._build_bond_pipeline()
    
    def filter_stocks(self, stocks: List[Dict]) -> List[Dict]:
        """过滤股票数据"""
        return self.stock_pipeline.execute(stocks)
    
    def filter_bonds(self, bonds: List[Dict]) -> List[Dict]:
        """过滤债券数据"""
        return self.bond_pipeline.execute(bonds)
    
    def _build_stock_pipeline(self) -> Pipeline:
        """构建股票过滤管道"""
        filters = []
        cfg = self.config.stock
        
        if cfg.industry:
            filters.append(IndustryFilter(cfg.industry))
        if cfg.topn_sectors:
            filters.append(TopNSectorsFilter(cfg.topn_sectors))
        if cfg.topn_sectors_pct:
            filters.append(TopNSectorsPctFilter(cfg.topn_sectors_pct))
        if cfg.topn_window:
            filters.append(TopNWindowFilter(cfg.topn_window))
        if cfg.topn_count:
            filters.append(TopNCountFilter(cfg.topn_count))
        if cfg.bond_filter:
            filters.append(BondExistsFilter())
        
        return Pipeline(filters)
    
    def _build_bond_pipeline(self) -> Pipeline:
        """构建债券过滤管道"""
        filters = []
        cfg = self.config.bond
        
        if cfg.industry:
            filters.append(IndustryFilter(cfg.industry))
        if cfg.topn_sectors:
            filters.append(TopNSectorsFilter(cfg.topn_sectors))
        if cfg.topn_sectors_pct:
            filters.append(TopNSectorsPctFilter(cfg.topn_sectors_pct))
        if cfg.topn_amount:
            filters.append(TopNAmountFilter(cfg.topn_amount))
        if cfg.topn_window:
            filters.append(TopNWindowFilter(cfg.topn_window))
        if cfg.topn_count:
            filters.append(TopNCountFilter(cfg.topn_count))
        if cfg.green_list:
            filters.append(GreenListFilter())
        
        return Pipeline(filters)
```

### 3. 前端改造

**当前前端逻辑**:
```javascript
// 当前：前端执行过滤
function rerenderStockRanking() {
    const rawData = _rankRawData['stock-ranking'];
    const filtered = runPipeline(STOCK_PIPELINE, rawData);  // 前端过滤
    renderRanking('stock-ranking', filtered);
}
```

**改造后前端逻辑**:
```javascript
// 改造后：后端执行过滤
async function rerenderStockRanking() {
    const filterConfig = buildFilterConfig();  // 收集配置
    const response = await fetch('/api/filter/stock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            date: getSelectedDate(),
            time: getSelectedTime(),
            filters: filterConfig.stock
        })
    });
    const result = await response.json();
    renderRanking('stock-ranking', result.data);
}
```

### 4. API 设计

#### 实时过滤查询

```http
POST /api/filter/stock
Content-Type: application/json

{
    "date": "20260803",
    "time": "10:30:00",
    "filters": {
        "industry": "电子",
        "topn_sectors": 5,
        "topn_window": 10
    }
}

Response:
{
    "success": true,
    "data": [...],  // 过滤后的股票列表
    "total": 20,
    "filter_info": {
        "applied": ["industry", "topn_sectors", "topn_window"],
        "before_count": 100,
        "after_count": 20
    }
}
```

```http
POST /api/filter/bond
Content-Type: application/json

{
    "date": "20260803",
    "time": "10:30:00",
    "filters": {
        "topn_amount": 20,
        "topn_window": 10
    }
}
```

#### 回溯任务（复用同一套 Pipeline）

```http
POST /api/backtrace/run
Content-Type: application/json

{
    "date": "20260803",
    "filters": {
        "stock": {
            "topn_sectors": 5,
            "topn_window": 10
        },
        "bond": {
            "topn_amount": 20,
            "topn_window": 10
        }
    }
}
```

**后端处理**:
```python
@api.route('/backtrace/run', methods=['POST'])
def run_backtrace():
    config = FilterConfig.from_dict(request.json['filters'])
    
    # 复用 UnifiedPipeline
    pipeline = UnifiedPipeline(config)
    
    for time_str in time_axis:
        stocks = fetch_stock_data(time_str)
        bonds = fetch_bond_data(time_str)
        
        # 同一套 Pipeline 过滤
        filtered_stocks = pipeline.filter_stocks(stocks)
        filtered_bonds = pipeline.filter_bonds(bonds)
        
        # 计算交集并保存...
```

### 5. 文件结构

```
src/gs2026/
├── common/                          # 共用模块（唯一维护点）
│   ├── __init__.py
│   ├── pipeline.py                  # UnifiedPipeline 统一过滤管道
│   ├── filters/
│   │   ├── __init__.py
│   │   ├── base.py                  # Filter 基类
│   │   ├── predicate.py             # 谓词型过滤器
│   │   ├── ranking.py               # 排名型过滤器
│   │   └── registry.py              # 过滤器注册表
│   └── config.py                    # FilterConfig 配置类
│
├── dashboard2/                      # 前端展示
│   └── templates/
│       └── monitor.html             # 改造：只收集配置，不调过滤逻辑
│
├── dashboard2/routes/               # API 路由
│   ├── filter_api.py                # 新增：/api/filter/*
│   └── backtrace_api.py             # 新增：/api/backtrace/*
│
└── tools/backtrace/                 # 回溯系统
    ├── __init__.py
    ├── runner.py                    # BacktraceRunner
    ├── time_axis.py                 # TimeAxisIterator
    ├── intersection.py              # IntersectionCalculator
    └── repository.py                # BacktraceRepository
```

### 6. 迁移计划

**阶段1：后端实现统一 Pipeline（3天）**
- [ ] 创建 `src/gs2026/common/pipeline.py`
- [ ] 实现所有过滤器（谓词型 + 排名型）
- [ ] 实现 FilterConfig 配置类
- [ ] 单元测试

**阶段2：新增过滤 API（2天）**
- [ ] 创建 `src/gs2026/dashboard2/routes/filter_api.py`
- [ ] 实现 `/api/filter/stock` 和 `/api/filter/bond`
- [ ] 联调测试

**阶段3：回溯系统实现（3天）**
- [ ] 创建回溯相关模块
- [ ] 复用 UnifiedPipeline
- [ ] 实现回溯 API

**阶段4：前端改造（2天）**
- [ ] 移除前端过滤逻辑
- [ ] 改为调用后端过滤 API
- [ ] 联调测试

**总计：10天**

## 优势

| 优势 | 说明 |
|------|------|
| **单一维护点** | 过滤逻辑只在后端实现一套 |
| **逻辑一致性** | 实时查询和回溯使用同一套逻辑 |
| **测试简化** | 只需测试后端过滤逻辑 |
| **前端简化** | 前端只负责 UI 和配置收集 |
| **易于扩展** | 新增过滤器只需改一处 |

## 风险与应对

| 风险 | 应对 |
|------|------|
| 前端改造成本 | 分阶段实施，先保证后端可用 |
| 性能影响（网络延迟） | 增加缓存，批量查询优化 |
| 向后兼容性 | 保留旧 API，逐步迁移 |

---

请审核此统一管道设计方案，确认后我完善到正式文档中。
