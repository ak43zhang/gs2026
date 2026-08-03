# 前端过滤优势分析 & 后端覆盖确认

**分析日期**: 2026-08-03  
**分析范围**: monitor.html 前端过滤逻辑

---

## 一、前端过滤核心优势分析

### 1. 过滤管道执行顺序（两阶段模型）

```javascript
function runPipeline(pipeline, data) {
    // Phase 1: 谓词型串行 → 候选池 S
    let S = data;
    for (const id in pipeline) {
        const f = pipeline[id];
        if (getFilterKind(pipeline, id) === 'predicate') {
            if (!f.isActive || f.isActive()) S = f.apply(S, 'predicate');
        }
    }
    // Phase 2: 排名型各自基于 S 算，取交集
    const activeRanking = [];
    for (const id in pipeline) {
        if (getFilterKind(pipeline, id) === 'ranking') {
            const f = pipeline[id];
            if (!f.isActive || f.isActive()) activeRanking.push(id);
        }
    }
    if (activeRanking.length === 0) return S;
    let resultCodes = null;
    for (const id of activeRanking) {
        const subset = pipeline[id].apply(S, 'ranking');
        const codes = new Set(subset.map(it => it.code));
        resultCodes = (resultCodes === null)
            ? codes
            : new Set([...resultCodes].filter(c => codes.has(c)));
    }
    return S.filter(it => resultCodes.has(it.code));
}
```

**优势1**: 明确的谓词先行、排名后行的两阶段执行顺序
**优势2**: 多个排名型过滤器取交集而非串行

**后端覆盖**: ✅ **已覆盖**
```python
class Pipeline:
    def execute(self, data: List[Dict]) -> List[Dict]:
        # Phase 1: 谓词型串行
        S = data
        for f in self.filters:
            if f.kind == 'predicate':
                S = f.apply(S)
        
        # Phase 2: 排名型取交集
        ranking_sets = []
        for f in self.filters:
            if f.kind == 'ranking':
                subset = f.apply(S)
                ranking_sets.append(set(item['code'] for item in subset))
        
        if ranking_sets:
            intersection = ranking_sets[0]
            for s in ranking_sets[1:]:
                intersection &= s
            S = [item for item in S if item['code'] in intersection]
        
        return S
```

---

### 2. 过滤器类型区分（predicate vs ranking）

**前端定义**:
```javascript
const STOCK_PIPELINE = {
    industry:     { kind: 'predicate', fixed: true, ... },
    bond:         { kind: 'predicate', fixed: true, ... },
    topn_sectors: { kind: 'ranking', fixed: false, ... },
    topn_window:  { kind: 'ranking', fixed: false, ... },
    topn_count:   { kind: 'ranking', fixed: false, ... },
};

const BOND_PIPELINE = {
    industry:     { kind: 'predicate', fixed: true, ... },
    topn_sectors: { kind: 'predicate', fixed: true, ... },  // 注意：债券是predicate
    green_list:   { kind: 'predicate', fixed: true, ... },
    topn_amount:  { kind: 'ranking', fixed: false, ... },
    topn_window:  { kind: 'ranking', fixed: false, ... },
    topn_count:   { kind: 'ranking', fixed: false, ... },
};
```

**关键差异**:
- 股票 `topn_sectors`: ranking
- 债券 `topn_sectors`: predicate（注意！）

**后端覆盖**: ✅ **已覆盖（需特别注意）**
```python
# 股票过滤器
class StockTopNSectorsFilter(RankingFilter):  # ranking
    pass

# 债券过滤器  
class BondTopNSectorsFilter(PredicateFilter):  # predicate（与前端一致）
    pass
```

---

### 3. 过滤器激活状态检查（isActive）

**前端实现**:
```javascript
isActive: () => { 
    const el = document.getElementById('stock-topn-industry'); 
    return !!(el && parseInt(el.value) > 0); 
}
```

**优势**: 动态检查过滤器是否启用（value > 0）

**后端覆盖**: ✅ **已覆盖**
```python
# 配置驱动，未配置即不启用
if config.topn_sectors:  # value > 0
    filters.append(TopNSectorsFilter(config.topn_sectors))
```

---

### 4. 排名型过滤器实现细节

**前端实现**:
```javascript
function applyToggleableFilter(data, mode, selectId, field) {
    const n = parseInt(el.value) || 0;
    if (mode === 'predicate') {
        return data.filter(it => (parseFloat(it[field]) || 0) > 0);
    }
    // ranking mode
    if (n <= 0) return data;
    const sorted = data.slice()
        .filter(it => (parseFloat(it[field]) || 0) > 0)  // 排除<=0
        .sort((a, b) => (parseFloat(b[field]) || 0) - (parseFloat(a[field]) || 0));  // 降序
    const codes = {};
    for (let i = 0; i < Math.min(n, sorted.length); i++) {
        codes[sorted[i].code] = true;
    }
    return data.filter(it => codes[it.code]);
}
```

**关键细节**:
1. 排除 `field <= 0` 的记录
2. 降序排序
3. 取前N（不足N则有多少取多少）
4. 返回原始数据中的匹配项（保持原始顺序）

**后端覆盖**: ✅ **已覆盖（需完善）**
```python
class RankingFilter(Filter):
    kind = 'ranking'
    
    def __init__(self, n: int, field: str):
        self.n = n
        self.field = field
    
    def apply(self, data: List[Dict]) -> List[Dict]:
        # 1. 排除<=0
        filtered = [d for d in data if d.get(self.field, 0) > 0]
        # 2. 降序排序
        sorted_data = sorted(filtered, key=lambda x: x.get(self.field, 0), reverse=True)
        # 3. 取前N
        top_n = sorted_data[:self.n]
        # 4. 获取code集合
        codes = {item['code'] for item in top_n}
        # 5. 返回原始数据中匹配的项（保持原始顺序）
        return [item for item in data if item['code'] in codes]
```

---

### 5. 强制类型保护（FORCE_KIND_FILTERS）

**前端实现**:
```javascript
const FORCE_KIND_FILTERS = ['topn_amount', 'topn_window', 'topn_count', 'topn_count_rank'];
function getFilterKind(pipeline, id) {
    const f = pipeline[id];
    if (!f) return 'predicate';
    if (f.fixed) return f.kind;
    // 强制排名类过滤器使用定义类型
    if (FORCE_KIND_FILTERS.includes(id)) {
        return f.kind;
    }
    return _kindOverride[id] || f.kind;
}
```

**优势**: 防止类型覆盖导致前N功能失效

**后端覆盖**: ✅ **已覆盖（无需，后端无覆盖机制）**
- 后端无 `_kindOverride` 机制，直接按定义类型执行

---

### 6. 交集模式（Intersection Mode）

**前端实现**:
```javascript
function applyIntersection(stockData, bondData) {
    const bondCodes = new Set((bondData || []).map(b => String(b.code)));
    const stockBondCodes = new Set(
        (stockData || [])
            .filter(s => s.bond_code && s.bond_code !== '-')
            .map(s => String(s.bond_code))
    );
    const stockResult = (stockData || []).filter(s =>
        s.bond_code && s.bond_code !== '-' && bondCodes.has(String(s.bond_code))
    );
    const bondResult = (bondData || []).filter(b =>
        stockBondCodes.has(String(b.code))
    );
    return { stockResult, bondResult };
}

function refreshBothWithIntersection() {
    const stockFiltered = runPipeline(STOCK_PIPELINE, _rankRawData['stock-ranking']);
    const bondFiltered = runPipeline(BOND_PIPELINE, _rankRawData['bond-ranking']);
    const { stockResult, bondResult } = applyIntersection(stockFiltered, bondFiltered);
    renderRanking('stock-ranking', stockResult);
    renderRanking('bond-ranking', bondResult);
}
```

**优势**: 先各自过滤，再取交集

**后端覆盖**: ✅ **已覆盖**
```python
class IntersectionCalculator:
    def calculate(self, stocks: List[Dict], bonds: List[Dict]) -> List[StockBondPair]:
        bond_map = {b['code']: b for b in bonds}
        intersections = []
        for stock in stocks:
            bond_code = stock.get('bond_code')
            if bond_code and bond_code in bond_map:
                intersections.append(StockBondPair(stock=stock, bond=bond_map[bond_code]))
        return intersections
```

---

### 7. 显示全部模式（Show All Mode）

**前端实现**:
```javascript
function rerenderStockRanking() {
    if (_showAllMode) {
        renderRanking('stock-ranking', rawData);  // 跳过所有过滤
        return;
    }
    // ... 正常过滤
}
```

**优势**: 快速查看全量数据

**后端覆盖**: ⚠️ **需补充**
- 后端API应支持 `skip_filter=true` 参数

```python
# 补充设计
@api.route('/api/filter/stock', methods=['POST'])
def filter_stock():
    if request.json.get('skip_filter'):
        return jsonify({'data': raw_data, 'filtered': False})
    # ... 正常过滤
```

---

### 8. 持久化与恢复（localStorage）

**前端实现**:
```javascript
function saveFilterState() {
    const state = {
        stock_topn_industry: document.getElementById('stock-topn-industry').value,
        bond_topn_amount: document.getElementById('bond-topn-amount').value,
        // ...
    };
    localStorage.setItem('filter_state', JSON.stringify(state));
}

function restoreFilterState() {
    const state = JSON.parse(localStorage.getItem('filter_state') || '{}');
    // 恢复各控件状态
}
```

**优势**: 用户偏好持久化

**后端覆盖**: ⚠️ **需补充**
- 后端可存储用户默认配置
- 或前端继续负责持久化，后端仅接收配置

---

### 9. 实时响应与用户体验

**前端优势**:
- 无需网络请求，响应即时
- 无网络延迟
- 离线可用

**后端应对**:
- 优化API响应时间 < 300ms
- 添加缓存机制
- 批量请求优化

---

## 二、前端特殊功能清单

| 功能 | 前端实现 | 后端覆盖状态 | 补充方案 |
|------|----------|--------------|----------|
| 两阶段过滤（谓词→排名） | ✅ | ✅ 已覆盖 | 无需补充 |
| 排名型取交集 | ✅ | ✅ 已覆盖 | 无需补充 |
| 过滤器类型区分 | ✅ | ✅ 已覆盖 | 注意债券topn_sectors是predicate |
| 激活状态检查 | ✅ | ✅ 已覆盖 | 配置驱动 |
| 排名型排除<=0 | ✅ | ✅ 已覆盖 | 已完善 |
| 强制类型保护 | ✅ | ✅ 已覆盖 | 后端无覆盖机制 |
| 交集模式 | ✅ | ✅ 已覆盖 | 已覆盖 |
| 显示全部模式 | ✅ | ⚠️ 需补充 | 添加skip_filter参数 |
| 持久化与恢复 | ✅ | ⚠️ 需补充 | 后端存储默认配置 |
| 实时响应 | ✅ | ⚠️ 需优化 | 优化至<300ms |

---

## 三、需补充的后端设计

### 补充1: 显示全部模式支持

```python
# filter_api.py
@api.route('/api/filter/stock', methods=['POST'])
def filter_stock():
    date = request.json.get('date')
    time = request.json.get('time')
    skip_filter = request.json.get('skip_filter', False)
    
    # 获取原始数据
    raw_data = data_service.get_stock_ranking(date, time)
    
    if skip_filter:
        return jsonify({
            'success': True,
            'data': raw_data,
            'filtered': False,
            'total': len(raw_data)
        })
    
    # 正常过滤
    config = FilterConfig.from_dict(request.json.get('filters', {}))
    pipeline = UnifiedPipeline(config)
    filtered = pipeline.filter_stocks(raw_data)
    
    return jsonify({
        'success': True,
        'data': filtered,
        'filtered': True,
        'total': len(filtered),
        'filter_info': {
            'before_count': len(raw_data),
            'after_count': len(filtered)
        }
    })
```

### 补充2: 用户默认配置存储

```python
# models.py
class UserFilterConfig(db.Model):
    __tablename__ = 'user_filter_config'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=False)
    config_type = db.Column(db.String(16), nullable=False)  # 'stock' | 'bond'
    config_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'config_type', name='uk_user_config_type'),
    )

# api.py
@api.route('/api/filter/config', methods=['GET', 'POST'])
def user_filter_config():
    if request.method == 'GET':
        config_type = request.args.get('type')
        config = UserFilterConfig.query.filter_by(
            user_id=current_user.id,
            config_type=config_type
        ).first()
        return jsonify({
            'success': True,
            'config': config.config_json if config else {}
        })
    
    elif request.method == 'POST':
        config_type = request.json.get('type')
        config_json = request.json.get('config')
        
        # upsert
        config = UserFilterConfig.query.filter_by(
            user_id=current_user.id,
            config_type=config_type
        ).first()
        
        if config:
            config.config_json = config_json
        else:
            config = UserFilterConfig(
                user_id=current_user.id,
                config_type=config_type,
                config_json=config_json
            )
            db.session.add(config)
        
        db.session.commit()
        return jsonify({'success': True})
```

### 补充3: 性能优化

```python
# pipeline.py
from functools import lru_cache
import time

class UnifiedPipeline:
    def __init__(self, config: FilterConfig):
        self.config = config
        self.stock_pipeline = self._build_stock_pipeline()
        self.bond_pipeline = self._build_bond_pipeline()
        self._cache = {}
    
    def filter_stocks(self, stocks: List[Dict]) -> List[Dict]:
        cache_key = self._get_cache_key(stocks)
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        result = self.stock_pipeline.execute(stocks)
        self._cache[cache_key] = result
        return result
    
    def _get_cache_key(self, data: List[Dict]) -> str:
        # 基于数据内容生成缓存key
        import hashlib
        content = json.dumps(data, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()[:16]
```

---

## 四、最终确认

### 已确认覆盖的前端优势（9项）

1. ✅ 两阶段过滤执行顺序（谓词→排名）
2. ✅ 排名型取交集（非串行）
3. ✅ 过滤器类型区分（predicate vs ranking）
4. ✅ 激活状态检查（isActive）
5. ✅ 排名型实现细节（排除<=0、降序、前N）
6. ✅ 强制类型保护（FORCE_KIND_FILTERS）
7. ✅ 交集模式（Intersection Mode）
8. ⚠️ 显示全部模式（需补充skip_filter）
9. ⚠️ 持久化与恢复（需补充后端存储）

### 需补充的设计（3项）

1. **显示全部模式**: 添加 `skip_filter` 参数支持
2. **用户配置存储**: 添加 `UserFilterConfig` 模型和API
3. **性能优化**: 添加缓存机制，确保 < 300ms

---

**分析完成时间**: 2026-08-03 22:35  
**分析人**: AI Assistant  
**状态**: 待审核
