# JSON字段快速回填方案 - 复用现有架构设计（v4）

## 一、问题确认

### 当前架构（正确）

```
monitor_bond.py 实时计算
      ↓
compute_engine.py 强制导入（_import_unified_functions）
      ↓
backfill_unified.py 回填计算
```

**关键设计**：`compute_engine.py` 强制从 `monitor_bond.py` 导入计算函数，确保实时和回填逻辑完全一致。

### 新方案的风险

如果新增 `backfill_json_fields.py` 独立实现 `compute_mkt_shape`，会导致：

```
monitor_bond.py 实时计算 ──┐
                            ├── 两套逻辑，维护困难
backfill_json_fields.py ────┘
```

**违反原始设计原则**：回填必须使用与实时计算完全一致的函数。

---

## 二、更优方案：复用现有架构

### 核心思想

**不新建 `backfill_json_fields.py`，而是扩展 `compute_engine.py` 支持JSON字段快速回填**。

```
monitor_bond.py 实时计算
      ↓
compute_engine.py 统一计算引擎（扩展支持JSON字段回填）
      ↓
backfill_unified.py 调用 compute_engine（已有）
      ↓
backfill_json_fields.py 轻量包装（调用 compute_engine）
```

### 方案对比

| 方案 | 计算逻辑位置 | 维护成本 | 是否符合原始设计 |
|------|-------------|---------|----------------|
| 独立实现 | `backfill_json_fields.py` 内嵌 | 高（两套） | ❌ 违反 |
| **复用架构** | `monitor_bond.py` → `compute_engine.py` | **低（一套）** | ✅ 符合 |

---

## 三、实施方案

### 3.1 扩展 `monitor_bond.py` 支持新JSON字段

**在 `monitor_bond.py` 中新增 `compute_mkt_shape` 函数**：

```python
# monitor_bond.py - 新增计算函数

def compute_mkt_shape(dependencies: Dict, history: List[Dict]) -> str:
    """
    计算大盘形态
    
    供实时计算和回填共用
    """
    if len(history) < 10:
        return '横盘'
    
    vs_values = [h.get('mkt_vs_open_pct', 0) for h in history]
    cur_pct = dependencies.get('mkt_vs_open_pct', 0)
    vs_values.append(cur_pct)
    
    high_pct = max(vs_values)
    low_pct = min(vs_values)
    total_range = high_pct - low_pct
    
    if total_range < 0.5:
        return '横盘'
    
    n = len(vs_values)
    high_idx = vs_values.index(high_pct)
    low_idx = vs_values.index(low_pct)
    high_pos = high_idx / (n - 1) if n > 1 else 0
    low_pos = low_idx / (n - 1) if n > 1 else 0
    
    sig = total_range * 0.5 if total_range > 0 else 0.001
    recovery = cur_pct - low_pct
    drawdown = high_pct - cur_pct
    
    if low_pos < 0.2 and cur_pct > 0 and drawdown < sig:
        return '单边上行'
    if high_pos < 0.2 and cur_pct < 0 and recovery < sig:
        return '单边下行'
    if low_pos > 0.2 and recovery > sig and cur_pct > 0:
        return '低开高走'
    if high_pos > 0.2 and drawdown > sig and cur_pct < 0:
        return '高开低走'
    
    return '横盘'


def compute_mkt_shape_detail(dependencies: Dict, history: List[Dict]) -> str:
    """计算大盘形态详情"""
    # ... 实现 ...
```

**在 `compute_mkt_trend_indicators` 中调用**：

```python
def compute_mkt_trend_indicators(df_now, time_full, current_date):
    # ... 原有计算 ...
    
    # 新增：计算形态
    mkt_shape_result = _compute_mkt_shape_local(
        mkt_vs_open_pct, time_full, current_date
    )
    
    return {
        # ... 原有字段 ...
        'mkt_shape': mkt_shape_result['shape'],
        'mkt_shape_detail': mkt_shape_result['detail'],
    }


def _compute_mkt_shape_local(mkt_vs_open_pct, time_full, current_date):
    """本地计算形态（使用全局状态）"""
    global _mkt_shape_date, _mkt_shape_history
    
    # 日期切换重置
    if _mkt_shape_date != current_date:
        _mkt_shape_history = []
        _mkt_shape_date = current_date
    
    # 添加当前点
    current_seconds = _time_to_seconds(time_full)
    _mkt_shape_history.append({
        'time': time_full,
        'time_sec': current_seconds,
        'vs_open': mkt_vs_open_pct
    })
    
    # 调用统一计算函数
    deps = {'mkt_vs_open_pct': mkt_vs_open_pct}
    history_for_calc = _mkt_shape_history[:-1]  # 不包括当前
    
    shape = compute_mkt_shape(deps, history_for_calc)
    detail = compute_mkt_shape_detail(deps, history_for_calc)
    
    return {'shape': shape, 'detail': detail}
```

### 3.2 扩展 `compute_engine.py` 支持JSON字段回填

**新增 `_compute_mkt_shape` 方法**：

```python
# compute_engine.py - 新增方法

class ComputeEngine:
    # ... 原有方法 ...
    
    def _compute_mkt_shape(self, mkt_vs_open_pct: float) -> dict:
        """
        计算大盘形态（回填专用）
        
        复用 monitor_bond.py 的统一计算函数
        """
        # 构建依赖和历史
        deps = {'mkt_vs_open_pct': mkt_vs_open_pct}
        
        # 历史从状态缓冲区构建
        history = []
        for t, p in self.mkt_trend_slope_10m_cache:
            history.append({'time_sec': t, 'mkt_vs_open_pct': p})
        
        # 调用 monitor_bond.py 的统一函数
        from monitor_bond import compute_mkt_shape, compute_mkt_shape_detail
        
        shape = compute_mkt_shape(deps, history)
        detail = compute_mkt_shape_detail(deps, history)
        
        return {
            'mkt_shape': shape,
            'mkt_shape_detail': detail
        }
```

### 3.3 简化 `backfill_json_fields.py`

**`backfill_json_fields.py` 只负责字段级UPDATE，计算逻辑复用 `compute_engine.py`**：

```python
#!/usr/bin/env python3
"""
JSON字段快速回填脚本（复用现有架构版）

核心特点：
- 计算逻辑复用 compute_engine.py（与实时计算一致）
- 只负责字段级JSON_SET更新
- 默认覆盖指定key

用法：
    python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape
    python backfill_json_fields.py --fields mkt_shape --skip-existing
"""

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Set

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from compute_engine import ComputeEngine  # 复用计算引擎
from gs2026.utils import config_util

DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
TABLE_PREFIX = "monitor_zq_sssj_"

# JSON字段配置（只声明依赖，计算函数在compute_engine中）
JSON_FIELDS = {
    'mkt_shape': {
        'depends': ['mkt_vs_open_pct'],
        'computer': '_compute_mkt_shape',  # ComputeEngine的方法名
        'needs_history': True,
    },
    'mkt_shape_detail': {
        'depends': ['mkt_vs_open_pct'],
        'computer': '_compute_mkt_shape_detail',
        'needs_history': True,
    },
}


class JsonFieldBackfiller:
    """JSON字段回填器（复用compute_engine）"""
    
    def __init__(self, db_url=None, workers=8):
        self.db_url = db_url or DB_URL
        self.workers = workers
        self.engine = self._create_engine()
    
    def _create_engine(self):
        return create_engine(
            self.db_url,
            pool_size=5, max_overflow=10,
            pool_recycle=3600, pool_pre_ping=True,
        )
    
    def backfill(self, dates: List[str], target_fields: List[str], skip_existing: bool = False):
        """批量回填"""
        valid_fields = [f for f in target_fields if f in JSON_FIELDS]
        if not valid_fields:
            print("[ERROR] 没有有效的字段")
            return
        
        all_deps = set()
        for f in valid_fields:
            all_deps.update(JSON_FIELDS[f]['depends'])
        
        print(f"[BACKFILL] {len(dates)} 天, 字段: {valid_fields}")
        print(f"[BACKFILL] 策略: {'跳过已有' if skip_existing else '默认覆盖'}")
        
        for date_str in dates:
            self._backfill_single_day(date_str, valid_fields, all_deps, skip_existing)
    
    def _backfill_single_day(self, date_str: str, target_fields: List[str], 
                            all_deps: Set[str], skip_existing: bool):
        """单日回填"""
        table_name = f"{TABLE_PREFIX}{date_str}"
        print(f"\n[{date_str}] 开始...")
        t0 = time.time()
        
        bonds = self._get_bonds(table_name)
        if not bonds:
            print(f"  [SKIP] 无数据")
            return
        
        print(f"  [INFO] {len(bonds)} 只债券")
        
        completed = failed = total_updates = 0
        
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(
                    self._process_bond_worker,
                    self.db_url, date_str, bond_code, target_fields, all_deps, skip_existing
                ): bond_code
                for bond_code in bonds
            }
            
            for future in as_completed(futures):
                bond_code = futures[future]
                try:
                    result = future.result()
                    if result['success']:
                        completed += 1
                        total_updates += result.get('updates', 0)
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                
                if (completed + failed) % 10 == 0:
                    print(f"  [PROGRESS] {completed + failed}/{len(bonds)} "
                          f"成功:{completed} 失败:{failed}")
        
        elapsed = time.time() - t0
        print(f"  [DONE] {completed} 成功, {failed} 失败, {total_updates} 更新, {elapsed:.1f}s")
    
    def _get_bonds(self, table_name: str) -> List[str]:
        """获取债券列表"""
        with self.engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT DISTINCT bond_code FROM `{table_name}`
                WHERE ext_indicators IS NOT NULL
            """))
            return [row[0] for row in result]
    
    @staticmethod
    def _process_bond_worker(db_url: str, date_str: str, bond_code: str,
                            target_fields: List[str], all_deps: Set[str],
                            skip_existing: bool) -> Dict:
        """处理单只债券"""
        try:
            engine = create_engine(db_url)
            table_name = f"{TABLE_PREFIX}{date_str}"
            
            # 读取数据
            with engine.connect() as conn:
                df = pd.read_sql(text(f"""
                    SELECT time, ext_indicators 
                    FROM `{table_name}`
                    WHERE bond_code = :code
                    ORDER BY time
                """), conn, params={'code': bond_code})
            
            if df.empty:
                return {'success': True, 'updates': 0}
            
            # 初始化计算引擎
            compute_engine = ComputeEngine()
            
            # 逐tick计算
            updates = []
            
            for _, row in df.iterrows():
                ext_json = row['ext_indicators']
                if not ext_json:
                    continue
                
                try:
                    ext = json.loads(ext_json)
                except:
                    ext = {}
                
                # skip_existing检查
                if skip_existing:
                    all_exist = all(f in ext for f in target_fields)
                    if all_exist:
                        # 更新计算引擎状态（不计算）
                        deps = {dep: ext.get(dep) for dep in all_deps}
                        compute_engine._update_state(deps)
                        continue
                
                # 提取依赖，更新计算引擎状态
                deps = {dep: ext.get(dep) for dep in all_deps}
                compute_engine._update_state(deps)
                
                # 计算目标字段（调用compute_engine的方法）
                field_values = {}
                for field_name in target_fields:
                    field_config = JSON_FIELDS[field_name]
                    computer_name = field_config['computer']
                    
                    # 获取计算函数
                    computer = getattr(compute_engine, computer_name)
                    
                    # 计算
                    if field_config['needs_history']:
                        value = computer(deps.get('mkt_vs_open_pct', 0))
                    else:
                        value = computer(deps)
                    
                    field_values[field_name] = value
                
                if field_values:
                    updates.append({
                        'time': row['time'],
                        'field_values': field_values
                    })
            
            # 批量UPDATE（JSON_SET）
            if updates:
                with engine.connect() as conn:
                    for upd in updates:
                        # 构建嵌套JSON_SET
                        set_expr = "ext_indicators"
                        params = []
                        
                        for field, value in upd['field_values'].items():
                            set_expr = f"JSON_SET({set_expr}, '$.{field}', %s)"
                            params.append(value)
                        
                        sql = f"""
                            UPDATE `{table_name}`
                            SET ext_indicators = {set_expr}
                            WHERE bond_code = %s AND time = %s
                        """
                        params.extend([bond_code, upd['time']])
                        conn.execute(text(sql), params)
                    
                    conn.commit()
            
            engine.dispose()
            return {'success': True, 'updates': len(updates)}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='单日 YYYYMMDD')
    parser.add_argument('--start', help='开始日期')
    parser.add_argument('--end', help='结束日期')
    parser.add_argument('--fields', nargs='+', required=True)
    parser.add_argument('--skip-existing', action='store_true')
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    
    # 日期范围
    if args.date:
        dates = [args.date]
    elif args.start and args.end:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT DISTINCT jyr FROM data_jyrl 
                WHERE jyr BETWEEN :start AND :end ORDER BY jyr
            """), {'start': args.start, 'end': args.end})
            dates = [row[0] for row in result]
        engine.dispose()
    else:
        print("[ERROR] 请指定--date或--start/--end")
        return
    
    backfiller = JsonFieldBackfiller(workers=args.workers)
    backfiller.backfill(dates, args.fields, args.skip_existing)
    print("\n[COMPLETE] 完成")


if __name__ == '__main__':
    main()
```

---

## 四、关键设计决策

### 4.1 计算逻辑统一

| 位置 | 职责 |
|------|------|
| `monitor_bond.py` | 定义计算函数（实时+回填共用） |
| `compute_engine.py` | 回填状态管理，调用monitor_bond的函数 |
| `backfill_json_fields.py` | 只负责字段级UPDATE，计算复用compute_engine |

### 4.2 与现有架构的整合

```
实时计算：
  monitor_bond.py::compute_mkt_trend_indicators()
    → 调用 compute_mkt_shape()（本地函数）
    → 写入 ext_indicators

回填计算：
  backfill_json_fields.py
    → 初始化 ComputeEngine
    → 逐tick调用 compute_engine._compute_mkt_shape()
      → ComputeEngine 内部调用 monitor_bond.compute_mkt_shape()
    → JSON_SET 更新 ext_indicators
```

**保证**：实时和回填使用完全相同的 `compute_mkt_shape` 函数。

### 4.3 扩展新JSON字段流程

1. **在 `monitor_bond.py` 中定义计算函数**：
```python
def compute_new_field(dependencies, history):
    """新字段计算（实时+回填共用）"""
    pass
```

2. **在 `compute_engine.py` 中添加回填方法**：
```python
def _compute_new_field(self, ...):
    """回填专用包装"""
    from monitor_bond import compute_new_field
    return compute_new_field(...)
```

3. **在 `backfill_json_fields.py` 中注册**：
```python
JSON_FIELDS = {
    'new_field': {
        'depends': ['dep1', 'dep2'],
        'computer': '_compute_new_field',
        'needs_history': True,
    },
}
```

---

## 五、与之前方案的对比

| 特性 | v3独立实现 | v4复用架构（当前） |
|------|-----------|------------------|
| 计算逻辑位置 | `backfill_json_fields.py` 内嵌 | `monitor_bond.py` → `compute_engine.py` |
| 维护成本 | 高（两套逻辑） | **低（一套逻辑）** |
| 是否符合原始设计 | ❌ 违反 | ✅ **符合** |
| 实时回填一致性 | 可能不一致 | **完全一致** |
| 扩展新字段 | 修改2处 | 修改3处（但逻辑一致） |

---

## 六、实施检查清单

- [ ] 在 `monitor_bond.py` 中新增 `compute_mkt_shape` 和 `compute_mkt_shape_detail`
- [ ] 在 `monitor_bond.py` 的 `compute_mkt_trend_indicators` 中调用新函数
- [ ] 在 `compute_engine.py` 中新增 `_compute_mkt_shape` 方法
- [ ] 创建 `backfill_json_fields.py`（复用compute_engine）
- [ ] 测试：实时计算和回填结果一致
- [ ] 测试：字段级JSON_SET只修改指定key
- [ ] 测试：--skip-existing模式

---

## 七、新增JSON字段配置清单

### 每新增一个JSON字段，需要修改以下配置

以新增 `mkt_trend_strength` 字段为例：

#### 1. monitor_bond.py（实时计算）

**A. 新增计算函数**：
```python
def compute_mkt_trend_strength(dependencies: Dict, history: List[Dict]) -> float:
    """
    计算趋势强度（实时+回填共用）
    
    Args:
        dependencies: {'mkt_weighted_slope_10m': float, 'mkt_vs_open_pct': float}
        history: 历史数据（如果需要）
    
    Returns:
        趋势强度值
    """
    slope = dependencies.get('mkt_weighted_slope_10m', 0)
    vs_open = dependencies.get('mkt_vs_open_pct', 0)
    # 计算逻辑...
    return strength
```

**B. 在实时计算中调用**：
```python
def compute_mkt_trend_indicators(df_now, time_full, current_date):
    # ... 原有计算 ...
    
    # 新增：计算趋势强度
    deps = {
        'mkt_weighted_slope_10m': mkt_weighted_slope_10m,
        'mkt_vs_open_pct': mkt_vs_open_pct,
    }
    mkt_trend_strength = compute_mkt_trend_strength(deps, history)
    
    return {
        # ... 原有字段 ...
        'mkt_trend_strength': mkt_trend_strength,  # 新增
    }
```

#### 2. compute_engine.py（回填引擎）

**A. 新增状态变量**（如果需要）：
```python
class ComputeEngine:
    def __init__(self):
        # ... 原有状态 ...
        self.mkt_trend_strength_cache = []  # 新增（如果需要）
```

**B. 新增回填计算方法**：
```python
def _compute_mkt_trend_strength(self, mkt_weighted_slope_10m: float, 
                                 mkt_vs_open_pct: float) -> float:
    """
    计算趋势强度（回填专用）
    
    复用 monitor_bond.py 的统一计算函数
    """
    from monitor_bond import compute_mkt_trend_strength
    
    deps = {
        'mkt_weighted_slope_10m': mkt_weighted_slope_10m,
        'mkt_vs_open_pct': mkt_vs_open_pct,
    }
    
    # 构建历史（如果需要）
    history = []
    
    return compute_mkt_trend_strength(deps, history)
```

**C. 在状态更新中维护缓存**（如果需要）：
```python
def _update_state(self, deps: Dict):
    # ... 原有状态更新 ...
    
    # 新增：更新趋势强度相关缓存
    if 'mkt_trend_strength' in deps:
        self.mkt_trend_strength_cache.append(deps['mkt_trend_strength'])
```

#### 3. backfill_json_fields.py（快速回填脚本）

**A. 在 JSON_FIELDS 中注册**：
```python
JSON_FIELDS = {
    # ... 已有字段 ...
    
    'mkt_trend_strength': {           # 新增
        'depends': ['mkt_weighted_slope_10m', 'mkt_vs_open_pct'],  # 依赖字段
        'computer': '_compute_mkt_trend_strength',  # compute_engine方法名
        'needs_history': False,         # 是否需要历史数据
    },
}
```

**B. 无需修改其他代码**（通用逻辑自动处理）

#### 4. field_registry.py（字段注册表）- 可选

如果字段需要在 `backfill_unified.py` 中支持：
```python
FIELD_REGISTRY = [
    # ... 已有字段 ...
    
    FieldDef(                         # 新增（可选）
        name='mkt_trend_strength',
        db_type='JSON',               # 存储在ext_indicators中
        category='ext_json',
        depends=['mkt_weighted_slope_10m', 'mkt_vs_open_pct'],
        description='趋势强度'
    ),
]
```

#### 5. 数据库 - 无需修改

JSON字段存储在 `ext_indicators` 列中，**不需要ALTER TABLE**。

---

### 配置修改汇总表

| 文件 | 修改内容 | 必需 |
|------|---------|------|
| `monitor_bond.py` | 新增计算函数 + 实时调用 | ✅ 必需 |
| `compute_engine.py` | 新增回填方法 + 状态管理 | ✅ 必需 |
| `backfill_json_fields.py` | JSON_FIELDS注册 | ✅ 必需 |
| `field_registry.py` | 字段定义（可选） | ❌ 可选 |
| 数据库 | 无需修改 | - |

---

## 八、总结

### 核心改进

**v3的问题**：独立实现计算逻辑，违反"回填必须使用与实时计算完全一致的函数"原则。

**v4的解决**：
1. 计算函数定义在 `monitor_bond.py`（实时+回填共用）
2. `compute_engine.py` 提供回填状态管理，调用monitor_bond的函数
3. `backfill_json_fields.py` 只负责字段级UPDATE，计算完全复用

### 架构图

```
┌─────────────────────────────────────────┐
│         monitor_bond.py                 │
│  ┌─────────────────────────────────┐   │
│  │ compute_mkt_shape()             │   │ ← 统一计算函数
│  │ compute_mkt_shape_detail()      │   │
│  └─────────────────────────────────┘   │
│              ↓ 实时调用                │
│  compute_mkt_trend_indicators()        │
└─────────────────────────────────────────┘
                    ↓ 强制导入
┌─────────────────────────────────────────┐
│       compute_engine.py                 │
│  ┌─────────────────────────────────┐   │
│  │ _compute_mkt_shape()            │   │ ← 回填包装
│  │   → 调用 monitor_bond 函数      │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                    ↓ 复用
┌─────────────────────────────────────────┐
│    backfill_json_fields.py              │
│  ┌─────────────────────────────────┐   │
│  │ 初始化 ComputeEngine            │   │
│  │ 调用 _compute_mkt_shape()        │   │
│  │ JSON_SET 更新指定字段           │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 保证

- ✅ **一套计算逻辑**：所有JSON字段计算在 `monitor_bond.py` 中定义
- ✅ **实时回填一致**：回填通过 `compute_engine` 调用相同的函数
- ✅ **字段级更新**：只修改指定key，不影响其他字段
- ✅ **高性能**：复用现有架构的优化（按债券并行等）

---

请审核方案，确认后实施。
