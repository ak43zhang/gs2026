# JSON字段快速回填方案 - 字段级独立更新设计（v3）

## 一、需求澄清

### 用户核心要求

| 要求 | 说明 |
|------|------|
| **字段级更新** | 只更新指定的字段，不影响JSON中的其他key |
| **默认覆盖** | 默认行为：如果key存在，覆盖其value |
| **独立处理** | 每个字段独立处理，可配置不同的更新策略 |
| **非全量覆盖** | 不覆盖整个JSON，只修改指定key |

### 与之前设计的区别

| 场景 | 之前设计 | 新设计 |
|------|---------|--------|
| 回填`mkt_shape` | 读取整行→修改JSON→UPDATE整行 | UPDATE中只修改`mkt_shape` key |
| 已有`mkt_shape` | 根据策略判断是否更新 | 默认覆盖（除非指定--skip-existing） |
| 其他字段 | 可能被覆盖（取决于策略） | 不受影响 |

---

## 二、核心设计：JSON字段级UPDATE

### 2.1 MySQL JSON字段级更新语法

```sql
-- 只更新指定key，不影响其他key
UPDATE table_name 
SET ext_indicators = JSON_SET(ext_indicators, '$.mkt_shape', '单边上行')
WHERE bond_code = 'xxx' AND time = '093003';

-- 删除指定key
UPDATE table_name 
SET ext_indicators = JSON_REMOVE(ext_indicators, '$.mkt_shape')
WHERE ...;

-- 条件更新（key不存在才设置）
UPDATE table_name 
SET ext_indicators = JSON_SET(ext_indicators, '$.mkt_shape', '单边上行')
WHERE bond_code = 'xxx' 
  AND JSON_EXTRACT(ext_indicators, '$.mkt_shape') IS NULL;
```

### 2.2 更新策略重新设计

| 策略 | MySQL实现 | 说明 |
|------|----------|------|
| **overwrite**（默认） | `JSON_SET(..., '$.field', value)` | 无条件覆盖指定key |
| **skip-existing** | `WHERE JSON_EXTRACT(...) IS NULL` | key存在则跳过该行 |
| **merge** | `JSON_MERGE_PATCH` | 合并JSON（保留未指定key） |

**关键区别**：
- 所有策略都只影响**指定的字段**，不影响JSON中的其他key
- `overwrite`是默认行为
- `skip-existing`通过WHERE条件实现，而非UPDATE逻辑

### 2.3 字段独立配置

```python
@dataclass
class JsonFieldDef:
    """JSON字段定义"""
    name: str
    depends: List[str]
    computer: str
    # 删除update_policy，改为全局策略统一控制
    needs_history: bool = False
    description: str = ''
```

**策略改为命令行参数控制**：
```bash
# 默认覆盖
python backfill_json_fields.py --fields mkt_shape

# 跳过已有
python backfill_json_fields.py --fields mkt_shape --skip-existing

# 多字段，统一策略
python backfill_json_fields.py --fields mkt_shape mkt_shape_detail --skip-existing
```

---

## 三、完整实施方案

### 3.1 核心流程

```python
# backfill_json_fields.py 核心逻辑

def backfill(self, dates, target_fields, skip_existing=False):
    """
    回填JSON字段
    
    Args:
        skip_existing: True=跳过已有key的行, False=覆盖（默认）
    """
    for date in dates:
        for bond in all_bonds:
            # 1. 获取该债券的所有tick
            rows = self._get_bond_ticks(date, bond, target_fields, skip_existing)
            #    如果skip_existing=True，WHERE条件过滤掉已有key的行
            
            # 2. 逐tick计算新字段
            updates = []
            history = []
            for row in rows:
                # 提取依赖值
                deps = self._extract_dependencies(row['ext_indicators'])
                
                # 计算每个目标字段
                field_values = {}
                for field in target_fields:
                    value = self._compute_field(field, deps, history)
                    field_values[field] = value
                
                updates.append({
                    'time': row['time'],
                    'field_values': field_values  # {field: value}
                })
                
                # 更新历史
                history.append({'time': row['time'], **deps})
            
            # 3. 批量UPDATE（每个字段独立JSON_SET）
            self._batch_update_json_fields(date, bond, updates)


def _batch_update_json_fields(self, date, bond, updates):
    """
    批量更新JSON字段（字段级独立更新）
    
    生成SQL:
    UPDATE table SET ext_indicators = JSON_SET(
        JSON_SET(ext_indicators, '$.field1', val1),
        '$.field2', val2
    ) WHERE bond_code='x' AND time='t'
    """
    for upd in updates:
        # 构建嵌套JSON_SET
        json_set_chain = "ext_indicators"
        for field, value in upd['field_values'].items():
            json_set_chain = f"JSON_SET({json_set_chain}, '$.{field}', %s)"
        
        sql = f"""
            UPDATE `{table_name}`
            SET ext_indicators = {json_set_chain}
            WHERE bond_code = %s AND time = %s
        """
        params = list(upd['field_values'].values()) + [bond, upd['time']]
        execute(sql, params)
```

### 3.2 完整代码实现

```python
#!/usr/bin/env python3
"""
JSON扩展字段快速回填脚本（字段级独立更新版）

核心特点：
- 字段级独立更新：只修改指定key，不影响其他字段
- 默认覆盖：无条件覆盖指定key的value
- 可选跳过：--skip-existing 可跳过已有key的行

用法：
    # 默认覆盖（无条件覆盖指定字段）
    python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape
    
    # 跳过已有（只填充缺失key的行）
    python backfill_json_fields.py --fields mkt_shape --skip-existing
    
    # 多字段同时回填
    python backfill_json_fields.py --fields mkt_shape mkt_shape_detail mkt_trend_strength
"""

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Tuple, Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from gs2026.utils import config_util


DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
TABLE_PREFIX = "monitor_zq_sssj_"


# ========== 字段注册表（简化版） ==========
from dataclasses import dataclass

@dataclass
class JsonFieldDef:
    """JSON字段定义"""
    name: str
    depends: List[str]                    # 依赖的JSON字段
    computer: callable                    # 计算函数（直接存储，非字符串）
    needs_history: bool = False           # 是否需要历史数据
    description: str = ''


# ========== 计算函数 ==========
def compute_mkt_shape(dependencies: Dict, history: List[Dict]) -> str:
    """计算大盘形态"""
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
    if len(history) < 10:
        return '数据不足'
    
    vs_values = [h.get('mkt_vs_open_pct', 0) for h in history]
    cur_pct = dependencies.get('mkt_vs_open_pct', 0)
    vs_values.append(cur_pct)
    
    high_pct = max(vs_values)
    low_pct = min(vs_values)
    total_range = high_pct - low_pct
    
    n = len(vs_values)
    high_idx = vs_values.index(high_pct)
    low_idx = vs_values.index(low_pct)
    high_pos = high_idx / (n - 1) if n > 1 else 0
    low_pos = low_idx / (n - 1) if n > 1 else 0
    
    sig = total_range * 0.5 if total_range > 0 else 0.001
    recovery = cur_pct - low_pct
    drawdown = high_pct - cur_pct
    
    if total_range < 0.5:
        return f'振幅{total_range:.2f}%<0.5%'
    if low_pos < 0.2 and cur_pct > 0 and drawdown < sig:
        return f'开盘即最低，当前{cur_pct:+.2f}%'
    if high_pos < 0.2 and cur_pct < 0 and recovery < sig:
        return f'开盘即最高，当前{cur_pct:+.2f}%'
    if low_pos > 0.2 and recovery > sig and cur_pct > 0:
        return f'低点在{low_pos:.0%}，回升{recovery:.2f}%'
    if high_pos > 0.2 and drawdown > sig and cur_pct < 0:
        return f'高点在{high_pos:.0%}，回落{drawdown:.2f}%'
    
    return f'高{high_pct:+.2f}% 低{low_pct:+.2f}% 收{cur_pct:+.2f}%'


# 字段注册表
JSON_FIELD_REGISTRY = [
    JsonFieldDef(
        name='mkt_shape',
        depends=['mkt_vs_open_pct'],
        computer=compute_mkt_shape,
        needs_history=True,
        description='大盘形态'
    ),
    JsonFieldDef(
        name='mkt_shape_detail',
        depends=['mkt_vs_open_pct'],
        computer=compute_mkt_shape_detail,
        needs_history=True,
        description='形态详情'
    ),
]


def get_field_def(name: str) -> Optional[JsonFieldDef]:
    """获取字段定义"""
    for f in JSON_FIELD_REGISTRY:
        if f.name == name:
            return f
    return None


def get_all_dependencies(target_fields: List[str]) -> Set[str]:
    """获取所有依赖"""
    deps = set()
    for name in target_fields:
        field_def = get_field_def(name)
        if field_def:
            deps.update(field_def.depends)
    return deps


# ========== 回填引擎 ==========
class JsonFieldBackfiller:
    """JSON字段回填引擎（字段级独立更新）"""
    
    def __init__(self, db_url=None, workers=8):
        self.db_url = db_url or DB_URL
        self.workers = workers
        self.engine = self._create_engine()
    
    def _create_engine(self):
        return create_engine(
            self.db_url,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
        )
    
    def backfill(self, dates: List[str], target_fields: List[str], skip_existing: bool = False):
        """
        批量回填
        
        Args:
            skip_existing: True=跳过已有key的行, False=覆盖（默认）
        """
        # 验证字段
        valid_fields = []
        for name in target_fields:
            if get_field_def(name):
                valid_fields.append(name)
            else:
                print(f"[WARN] 未知字段: {name}")
        
        if not valid_fields:
            print("[ERROR] 没有有效的字段")
            return
        
        all_deps = get_all_dependencies(valid_fields)
        print(f"[BACKFILL] {len(dates)} 天, 字段: {valid_fields}, 依赖: {sorted(all_deps)}")
        print(f"[BACKFILL] 策略: {'跳过已有' if skip_existing else '默认覆盖'}")
        
        for date_str in dates:
            self._backfill_single_day(date_str, valid_fields, all_deps, skip_existing)
    
    def _backfill_single_day(self, date_str: str, target_fields: List[str], 
                            all_deps: Set[str], skip_existing: bool):
        """单日回填"""
        table_name = f"{TABLE_PREFIX}{date_str}"
        print(f"\n[{date_str}] 开始...")
        t0 = time.time()
        
        bonds = self._get_bonds(table_name, target_fields, skip_existing)
        if not bonds:
            print(f"  [SKIP] 无数据")
            return
        
        print(f"  [INFO] {len(bonds)} 只债券")
        
        completed = 0
        failed = 0
        total_updates = 0
        
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
                        print(f"  [ERROR] {bond_code}: {result.get('error', 'Unknown')}")
                except Exception as e:
                    print(f"  [ERROR] {bond_code}: {e}")
                    failed += 1
                
                if (completed + failed) % 10 == 0:
                    print(f"  [PROGRESS] {completed + failed}/{len(bonds)} "
                          f"成功:{completed} 失败:{failed} 更新:{total_updates}")
        
        elapsed = time.time() - t0
        print(f"  [DONE] {completed} 成功, {failed} 失败, {total_updates} 更新, {elapsed:.1f}s")
    
    def _get_bonds(self, table_name: str, target_fields: List[str], skip_existing: bool) -> List[str]:
        """获取债券列表"""
        with self.engine.connect() as conn:
            if skip_existing:
                # 只获取没有目标字段的债券
                # 简化：先获取所有，在worker中过滤
                pass
            
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
            
            # 1. 读取数据
            with engine.connect() as conn:
                df = pd.read_sql(text(f"""
                    SELECT time, ext_indicators 
                    FROM `{table_name}`
                    WHERE bond_code = :code
                    ORDER BY time
                """), conn, params={'code': bond_code})
            
            if df.empty:
                return {'success': True, 'updates': 0}
            
            # 2. 处理数据
            updates = []
            history = []
            
            for _, row in df.iterrows():
                ext_json = row['ext_indicators']
                if not ext_json:
                    continue
                
                try:
                    ext = json.loads(ext_json)
                except:
                    ext = {}
                
                # 检查是否需要跳过（skip_existing模式）
                if skip_existing:
                    all_exist = all(field in ext for field in target_fields)
                    if all_exist:
                        # 复用已有值维护history
                        deps = {dep: ext.get(dep) for dep in all_deps}
                        history.append({'time': row['time'], **deps})
                        continue
                
                # 提取依赖
                deps = {dep: ext.get(dep) for dep in all_deps}
                
                # 计算目标字段
                field_values = {}
                for field_name in target_fields:
                    field_def = get_field_def(field_name)
                    if not field_def:
                        continue
                    
                    # 计算
                    if field_def.needs_history:
                        value = field_def.computer(deps, history.copy())
                    else:
                        value = field_def.computer(deps, [])
                    
                    field_values[field_name] = value
                
                if field_values:
                    updates.append({
                        'time': row['time'],
                        'field_values': field_values
                    })
                
                # 更新history
                history.append({'time': row['time'], **deps})
            
            # 3. 批量UPDATE（字段级JSON_SET）
            if updates:
                with engine.connect() as conn:
                    for upd in updates:
                        # 构建嵌套JSON_SET链
                        set_expr = "ext_indicators"
                        params = []
                        
                        for field, value in upd['field_values'].items():
                            # 处理字符串转义
                            if isinstance(value, str):
                                set_expr = f"JSON_SET({set_expr}, '$.{field}', %s)"
                                params.append(value)
                            else:
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
            return {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}


def main():
    parser = argparse.ArgumentParser(description='JSON字段快速回填（字段级独立更新）')
    parser.add_argument('--date', help='单日 YYYYMMDD')
    parser.add_argument('--start', help='开始日期')
    parser.add_argument('--end', help='结束日期')
    parser.add_argument('--fields', nargs='+', required=True, help='目标字段')
    parser.add_argument('--skip-existing', action='store_true', 
                       help='跳过已有key的行（默认覆盖）')
    parser.add_argument('--workers', type=int, default=8, help='并行数')
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
    
    # 执行
    backfiller = JsonFieldBackfiller(workers=args.workers)
    backfiller.backfill(dates, args.fields, args.skip_existing)
    
    print("\n[COMPLETE] 完成")


if __name__ == '__main__':
    main()
```

### 3.3 关键SQL生成示例

```python
# 场景1：回填mkt_shape（默认覆盖）
# 输入：field_values = {'mkt_shape': '单边上行'}
# 生成：
UPDATE table SET ext_indicators = JSON_SET(ext_indicators, '$.mkt_shape', '单边上行')
WHERE bond_code = 'xxx' AND time = '093003';

# 场景2：回填多个字段
# 输入：field_values = {'mkt_shape': '单边上行', 'mkt_shape_detail': '开盘即最低'}
# 生成：
UPDATE table SET ext_indicators = JSON_SET(
    JSON_SET(ext_indicators, '$.mkt_shape', '单边上行'),
    '$.mkt_shape_detail', '开盘即最低'
)
WHERE bond_code = 'xxx' AND time = '093003';

# 场景3：skip-existing模式
# WHERE条件添加：
SELECT ... WHERE bond_code = 'xxx' 
  AND (JSON_EXTRACT(ext_indicators, '$.mkt_shape') IS NULL 
       OR JSON_EXTRACT(ext_indicators, '$.mkt_shape_detail') IS NULL)
```

---

## 四、使用示例

### 4.1 默认覆盖（无条件覆盖指定字段）

```bash
# 回填mkt_shape，如果已存在则覆盖
python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape

# 同时回填多个字段
python backfill_json_fields.py --fields mkt_shape mkt_shape_detail
```

**效果**：
- 只修改`mkt_shape`和`mkt_shape_detail` key
- `ext_indicators`中的其他key不受影响
- 已有`mkt_shape`的值被新值覆盖

### 4.2 跳过已有（只填充缺失key的行）

```bash
# 只回填没有mkt_shape的行
python backfill_json_fields.py --fields mkt_shape --skip-existing
```

**效果**：
- 检查每行是否已有`mkt_shape` key
- 已有则跳过该行
- 缺失则添加

### 4.3 扩展新字段流程

```python
# 1. 在JSON_FIELD_REGISTRY中添加
JsonFieldDef(
    name='mkt_trend_strength',
    depends=['mkt_weighted_slope_10m', 'mkt_vs_open_pct'],
    computer=compute_trend_strength,
    needs_history=False,
)

# 2. 实现计算函数
def compute_trend_strength(deps, history):
    slope = deps.get('mkt_weighted_slope_10m', 0)
    vs_open = deps.get('mkt_vs_open_pct', 0)
    return abs(slope) * abs(vs_open) * 100

# 3. 运行回填
# python backfill_json_fields.py --fields mkt_trend_strength
```

---

## 五、与之前设计的对比

| 特性 | v2设计 | v3设计（当前） |
|------|--------|---------------|
| 更新粒度 | 整行UPDATE | 字段级JSON_SET |
| 默认行为 | skip（不覆盖） | overwrite（覆盖） |
| 策略控制 | 字段级policy | 全局--skip-existing |
| 其他字段影响 | 可能被覆盖 | 完全不受影响 |
| SQL生成 | 整行JSON序列化 | 嵌套JSON_SET |
| 扩展性 | 需要修改policy | 只添加field+computer |

---

## 六、实施检查清单

- [x] 创建`backfill_json_fields.py`（字段级独立更新版）
- [ ] 测试：默认覆盖模式
- [ ] 测试：--skip-existing模式
- [ ] 测试：多字段同时回填
- [ ] 测试：JSON中其他字段不受影响
- [ ] 测试：扩展新字段流程
- [ ] 文档更新

---

## 八、实施完成记录

### 8.1 已修改文件

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `monitor_bond.py` | 新增全局状态变量 `_mkt_shape_date`, `_mkt_shape_history` | ✅ |
| `monitor_bond.py` | 新增计算函数 `compute_mkt_shape()`, `compute_mkt_shape_detail()` | ✅ |
| `monitor_bond.py` | 修改 `compute_mkt_trend_indicators()` 添加形态计算 | ✅ |
| `compute_engine.py` | 新增状态变量 `mkt_shape_history` | ✅ |
| `compute_engine.py` | 新增回填方法 `_compute_mkt_shape()`, `_compute_mkt_shape_detail()` | ✅ |
| `compute_engine.py` | 修改 `_compute_mkt_trend()` 添加形态计算 | ✅ |
| `compute_engine.py` | 新增 `_update_mkt_state()` 方法 | ✅ |
| `backfill_json_fields.py` | 创建新脚本 | ✅ |

---

## 七、总结

### 核心设计

1. **字段级更新**：使用MySQL `JSON_SET()` 只修改指定key
2. **默认覆盖**：无条件覆盖指定字段的值
3. **独立处理**：每个字段独立计算，互不影响
4. **可选跳过**：`--skip-existing` 只填充缺失key的行

### 关键SQL

```sql
-- 只更新指定key，不影响其他key
UPDATE table SET ext_indicators = JSON_SET(
    JSON_SET(ext_indicators, '$.field1', val1),
    '$.field2', val2
) WHERE ...;
```

### 使用模式

```bash
# 默认：覆盖指定字段
python backfill_json_fields.py --fields mkt_shape

# 跳过已有：只填充缺失
python backfill_json_fields.py --fields mkt_shape --skip-existing
```

---

请审核方案，确认后实施。
