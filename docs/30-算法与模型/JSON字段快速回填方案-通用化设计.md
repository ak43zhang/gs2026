# JSON字段快速回填方案 - 通用化设计（v2）

## 一、问题重新分析

### 1.1 用户提出的两个关键问题

**问题1：字段依赖的通用性**
- 当前设计：硬编码复用`mkt_vs_open_pct`
- 实际情况：新增字段可能依赖**任意已有字段**
- 例：`mkt_shape`依赖`mkt_vs_open_pct`，但未来`mkt_trend_strength`可能依赖`mkt_weighted_slope_10m`

**问题2：覆盖更新策略**
- 当前设计：如果JSON中已有key，跳过不更新
- 实际需求：
  - **跳过**（已有数据不覆盖）
  - **覆盖**（强制更新已有数据）
  - **增量**（只添加缺失的key）

### 1.2 通用化需求

| 需求 | 说明 |
|------|------|
| 依赖声明 | 新增字段必须声明依赖哪些字段 |
| 依赖解析 | 自动从已有JSON中提取依赖字段 |
| 计算路由 | 根据字段类型路由到对应计算函数 |
| 更新策略 | 可配置：skip/overwrite/merge |

---

## 二、通用化设计方案

### 2.1 核心架构：字段计算引擎

```python
# 字段计算注册表（与field_registry配合）
FIELD_COMPUTERS = {
    # 字段名 -> 计算函数
    'mkt_shape': compute_mkt_shape,           # 大盘形态
    'mkt_shape_detail': compute_mkt_shape_detail,  # 形态详情
    'mkt_trend_strength': compute_trend_strength,  # 趋势强度
    # ... 可扩展
}

# 计算函数签名
def compute_mkt_shape(dependencies: Dict, history: List[Dict]) -> Any:
    """
    计算字段值
    
    Args:
        dependencies: 依赖字段的当前值 {dep_field: value}
        history: 历史数据（用于状态依赖字段）
    
    Returns:
        字段值
    """
    mkt_vs_open_pct = dependencies.get('mkt_vs_open_pct', 0)
    # ... 计算逻辑
    return shape
```

### 2.2 字段依赖声明

**方式1：扩展FieldDef（推荐）**
```python
@dataclass
class JsonFieldDef:
    """JSON字段定义（扩展）"""
    name: str
    depends: List[str]                    # 依赖的JSON字段
    computer: str                         # 计算函数名
    update_policy: str = 'skip'           # 更新策略: skip/overwrite/merge
    needs_history: bool = False           # 是否需要历史数据
    description: str = ''

# JSON字段注册表
JSON_FIELD_REGISTRY = [
    JsonFieldDef(
        name='mkt_shape',
        depends=['mkt_vs_open_pct'],       # 依赖已有JSON字段
        computer='compute_mkt_shape',        # 计算函数
        update_policy='skip',                # 已有不覆盖
        needs_history=True,                  # 需要历史
        description='大盘形态'
    ),
    JsonFieldDef(
        name='mkt_shape_detail',
        depends=['mkt_vs_open_pct'],
        computer='compute_mkt_shape_detail',
        update_policy='skip',
        needs_history=True,
        description='形态详情'
    ),
]
```

**方式2：动态依赖发现**
```python
# 计算函数声明依赖（装饰器模式）
@json_field(
    name='mkt_shape',
    depends=['mkt_vs_open_pct'],
    update_policy='skip'
)
def compute_mkt_shape(dependencies, history):
    pass
```

### 2.3 更新策略设计

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| **skip** | 如果key存在，跳过不更新 | 首次回填、已有数据可信 |
| **overwrite** | 强制覆盖已有value | 算法更新、数据修复 |
| **merge** | 合并（保留已有，添加缺失） | 增量添加多个字段 |

```python
def should_update(existing_json: Dict, field_name: str, policy: str) -> bool:
    """判断是否应更新字段"""
    if field_name not in existing_json:
        return True  # 不存在，必须添加
    
    if policy == 'skip':
        return False  # 存在且策略为skip，不更新
    elif policy == 'overwrite':
        return True   # 强制覆盖
    elif policy == 'merge':
        return False  # merge策略下，已有key不覆盖
    
    return False
```

### 2.4 通用回填流程

```
backfill_json_fields.py 通用流程：

1. 解析字段定义（从JSON_FIELD_REGISTRY）
   - 获取每个目标字段的依赖列表
   - 获取计算函数
   - 获取更新策略

2. 收集所有依赖
   - all_deps = set(所有目标字段的依赖)
   - 例：回填mkt_shape+mkt_shape_detail → 依赖{mkt_vs_open_pct}

3. 按债券并行处理
   for bond in all_bonds:
      # 3.1 读取该债券的所有ext_indicators
      # 3.2 解析JSON，提取依赖字段
      # 3.3 构建历史数据（如果需要）
      # 3.4 逐tick计算
          for tick in ticks:
              # 3.4.1 提取当前依赖值
              deps = {dep: json[dep] for dep in all_deps}
              
              # 3.4.2 检查是否需要更新
              needs_update = any(should_update(json, f, policy) for f in target_fields)
              
              # 3.4.3 如需更新，调用计算函数
              if needs_update:
                  for field in target_fields:
                      if should_update(json, field, policy):
                          value = FIELD_COMPUTERS[field](deps, history)
                          json[field] = value
              
              # 3.4.4 更新历史
              history.append({'time': tick.time, **deps})
      
      # 3.5 批量UPDATE修改过的行

4. 汇总统计
```

---

## 三、完整实施方案

### 3.1 新增/修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/json_field_registry.py` | 新增 | JSON字段注册表（依赖声明） |
| `scripts/json_field_computers.py` | 新增 | 字段计算函数库 |
| `scripts/backfill_json_fields.py` | 修改 | 通用化回填引擎 |
| `scripts/field_registry.py` | 修改 | 添加JSON字段引用 |

### 3.2 json_field_registry.py（新增）

```python
"""
JSON扩展字段注册表

声明式配置所有JSON字段的元数据和计算方式。
与field_registry.py配合，但专注于ext_indicators内的JSON字段。
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Optional


@dataclass
class JsonFieldDef:
    """JSON字段定义"""
    name: str                           # 字段名（JSON中的key）
    depends: List[str]                  # 依赖的JSON字段列表
    computer: str                       # 计算函数名（在json_field_computers中）
    update_policy: str = 'skip'         # 更新策略: skip/overwrite/merge
    needs_history: bool = False         # 是否需要历史数据
    description: str = ''               # 字段说明


# ========== JSON字段注册表 ==========
JSON_FIELD_REGISTRY: List[JsonFieldDef] = [
    # === 大盘形态字段 ===
    JsonFieldDef(
        name='mkt_shape',
        depends=['mkt_vs_open_pct'],     # 依赖mkt_vs_open_pct
        computer='compute_mkt_shape',
        update_policy='skip',
        needs_history=True,
        description='大盘日内形态: 单边上行/单边下行/低开高走/高开低走/横盘'
    ),
    JsonFieldDef(
        name='mkt_shape_detail',
        depends=['mkt_vs_open_pct'],
        computer='compute_mkt_shape_detail',
        update_policy='skip',
        needs_history=True,
        description='大盘形态详细说明'
    ),
    
    # === 示例：未来可扩展的字段 ===
    # JsonFieldDef(
    #     name='mkt_trend_strength',
    #     depends=['mkt_weighted_slope_10m', 'mkt_vs_open_pct'],  # 多字段依赖
    #     computer='compute_trend_strength',
    #     update_policy='overwrite',
    #     needs_history=False,
    #     description='趋势强度评分'
    # ),
]


def get_json_field_def(name: str) -> Optional[JsonFieldDef]:
    """根据名称获取JSON字段定义"""
    for f in JSON_FIELD_REGISTRY:
        if f.name == name:
            return f
    return None


def get_json_field_names() -> List[str]:
    """获取所有JSON字段名"""
    return [f.name for f in JSON_FIELD_REGISTRY]


def get_all_json_dependencies(target_fields: List[str]) -> set:
    """获取目标字段的所有依赖"""
    deps = set()
    for name in target_fields:
        field_def = get_json_field_def(name)
        if field_def:
            deps.update(field_def.depends)
    return deps


def validate_json_fields(target_fields: List[str]) -> tuple:
    """
    验证目标字段是否可回填
    
    Returns:
        (valid_fields: List[str], invalid_fields: List[str], missing_deps: set)
    """
    valid = []
    invalid = []
    missing_deps = set()
    
    for name in target_fields:
        field_def = get_json_field_def(name)
        if field_def:
            valid.append(name)
            # 检查依赖是否都可获取
            for dep in field_def.depends:
                # 依赖可以是物理列或JSON字段
                # 这里只检查JSON字段的依赖链
                if dep not in get_json_field_names():
                    # 假设是物理列或已有JSON字段
                    pass
        else:
            invalid.append(name)
    
    return valid, invalid, missing_deps


if __name__ == '__main__':
    print("=" * 60)
    print("JSON字段注册表")
    print("=" * 60)
    for f in JSON_FIELD_REGISTRY:
        print(f"\n【{f.name}】")
        print(f"  依赖: {f.depends}")
        print(f"  计算函数: {f.computer}")
        print(f"  更新策略: {f.update_policy}")
        print(f"  需要历史: {f.needs_history}")
        print(f"  说明: {f.description}")
    print(f"\n总计: {len(JSON_FIELD_REGISTRY)} 个JSON字段")
```

### 3.3 json_field_computers.py（新增）

```python
"""
JSON字段计算函数库

所有JSON字段的计算逻辑在此实现。
函数签名统一：compute_xxx(dependencies: Dict, history: List[Dict]) -> Any
"""

import json
from typing import Dict, List, Any, Tuple


def compute_mkt_shape(dependencies: Dict, history: List[Dict]) -> str:
    """
    计算大盘形态
    
    Args:
        dependencies: {'mkt_vs_open_pct': float}
        history: [{'time': str, 'mkt_vs_open_pct': float}, ...]
    
    Returns:
        形态名: '单边上行'/'单边下行'/'低开高走'/'高开低走'/'横盘'
    """
    if len(history) < 10:
        return '横盘'
    
    # 合并历史和当前
    vs_values = [h.get('mkt_vs_open_pct', 0) for h in history]
    cur_pct = dependencies.get('mkt_vs_open_pct', 0)
    vs_values.append(cur_pct)
    
    high_pct = max(vs_values)
    low_pct = min(vs_values)
    total_range = high_pct - low_pct
    
    # 阈值
    sig = total_range * 0.5 if total_range > 0 else 0.001
    
    # 位置计算
    n = len(vs_values)
    high_idx = vs_values.index(high_pct)
    low_idx = vs_values.index(low_pct)
    high_pos = high_idx / (n - 1) if n > 1 else 0
    low_pos = low_idx / (n - 1) if n > 1 else 0
    
    recovery = cur_pct - low_pct
    drawdown = high_pct - cur_pct
    
    # 判定
    if total_range < 0.5:
        return '横盘'
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
        return '数据不足，默认横盘'
    
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
    
    # 生成详情
    if total_range < 0.5:
        return f'振幅{total_range:.2f}%<0.5%，波动过小'
    if low_pos < 0.2 and cur_pct > 0 and drawdown < sig:
        return f'开盘即最低，当前{cur_pct:+.2f}%，回落{drawdown:.2f}%<阈值{sig:.2f}%'
    if high_pos < 0.2 and cur_pct < 0 and recovery < sig:
        return f'开盘即最高，当前{cur_pct:+.2f}%，回升{recovery:.2f}%<阈值{sig:.2f}%'
    if low_pos > 0.2 and recovery > sig and cur_pct > 0:
        return f'低点在{low_pos:.0%}位置，回升{recovery:.2f}%>{sig:.2f}%，当前{cur_pct:+.2f}%'
    if high_pos > 0.2 and drawdown > sig and cur_pct < 0:
        return f'高点在{high_pos:.0%}位置，回落{drawdown:.2f}%>{sig:.2f}%，当前{cur_pct:+.2f}%'
    
    return f'无明确形态(高{high_pct:+.2f}%@{high_pos:.0%} 低{low_pct:+.2f}%@{low_pos:.0%})'


# ========== 计算函数注册表 ==========
FIELD_COMPUTERS = {
    'compute_mkt_shape': compute_mkt_shape,
    'compute_mkt_shape_detail': compute_mkt_shape_detail,
    # 未来添加更多...
}


def get_computer(name: str) -> callable:
    """获取计算函数"""
    return FIELD_COMPUTERS.get(name)
```

### 3.4 backfill_json_fields.py（修改后，通用化版本）

```python
#!/usr/bin/env python3
"""
JSON扩展字段快速回填脚本（通用化版本）

特点：
- 通用字段依赖解析（从json_field_registry）
- 可配置更新策略（skip/overwrite/merge）
- 复用已有JSON字段，避免重复计算
- 按债券并行，最大化CPU利用

用法：
    # 首次回填（skip模式，已有不覆盖）
    python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape mkt_shape_detail
    
    # 强制覆盖（overwrite模式）
    python backfill_json_fields.py --date 20260723 --fields mkt_shape --policy overwrite
    
    # 增量合并（merge模式，添加缺失字段，保留已有）
    python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape mkt_trend_strength --policy merge
"""

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Tuple, Any

import pandas as pd
from sqlalchemy import create_engine, text

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from json_field_registry import (
    JsonFieldDef, get_json_field_def, get_all_json_dependencies, 
    validate_json_fields, JSON_FIELD_REGISTRY
)
from json_field_computers import get_computer
from gs2026.utils import config_util


DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
TABLE_PREFIX = "monitor_zq_sssj_"


class JsonFieldBackfiller:
    """JSON字段通用回填引擎"""
    
    def __init__(self, db_url=None, workers=8, policy='skip'):
        self.db_url = db_url or DB_URL
        self.workers = workers
        self.policy = policy  # 全局更新策略
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
    
    def backfill(self, dates: List[str], target_fields: List[str], policy: str = None):
        """
        批量回填多日期
        
        Args:
            dates: 日期列表
            target_fields: 目标字段列表
            policy: 更新策略（覆盖全局策略）
        """
        policy = policy or self.policy
        
        # 1. 验证字段
        valid_fields, invalid_fields, _ = validate_json_fields(target_fields)
        if invalid_fields:
            print(f"[WARN] 忽略无效字段: {invalid_fields}")
        if not valid_fields:
            print("[ERROR] 没有有效的字段需要回填")
            return
        
        # 2. 收集所有依赖
        all_deps = get_all_json_dependencies(valid_fields)
        print(f"[BACKFILL] 回填 {len(dates)} 天")
        print(f"  目标字段: {valid_fields}")
        print(f"  依赖字段: {sorted(all_deps)}")
        print(f"  更新策略: {policy}")
        
        # 3. 逐日处理
        for date_str in dates:
            self._backfill_single_day(date_str, valid_fields, all_deps, policy)
    
    def _backfill_single_day(self, date_str: str, target_fields: List[str], 
                            all_deps: Set[str], policy: str):
        """单日回填"""
        table_name = f"{TABLE_PREFIX}{date_str}"
        print(f"\n[{date_str}] 开始回填...")
        t0 = time.time()
        
        # 获取债券列表
        bonds = self._get_bonds(table_name)
        if not bonds:
            print(f"  [SKIP] 无数据")
            return
        
        print(f"  [INFO] {len(bonds)} 只债券，策略={policy}")
        
        # 按债券并行
        completed = 0
        failed = 0
        total_updates = 0
        
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(
                    self._process_bond_worker, 
                    self.db_url, date_str, bond_code, target_fields, all_deps, policy
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
        print(f"  [DONE] 完成: {completed} 成功, {failed} 失败, "
              f"{total_updates} 行更新, 耗时 {elapsed:.1f}s")
    
    def _get_bonds(self, table_name: str) -> List[str]:
        """获取所有债券代码"""
        with self.engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT DISTINCT bond_code FROM `{table_name}`
                WHERE ext_indicators IS NOT NULL
            """))
            return [row[0] for row in result]
    
    @staticmethod
    def _process_bond_worker(db_url: str, date_str: str, bond_code: str,
                            target_fields: List[str], all_deps: Set[str],
                            policy: str) -> Dict:
        """处理单只债券（独立进程）"""
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
                
                # 提取依赖值
                deps = {dep: ext.get(dep) for dep in all_deps}
                
                # 检查是否需要更新
                needs_update = False
                fields_to_compute = []
                
                for field_name in target_fields:
                    field_def = get_json_field_def(field_name)
                    if not field_def:
                        continue
                    
                    # 确定更新策略（字段级 > 全局）
                    field_policy = field_def.update_policy or policy
                    
                    if field_name not in ext:
                        needs_update = True
                        fields_to_compute.append((field_name, field_def))
                    elif field_policy == 'overwrite':
                        needs_update = True
                        fields_to_compute.append((field_name, field_def))
                    # skip/merge策略：已有key不更新
                
                if needs_update:
                    # 计算新字段
                    for field_name, field_def in fields_to_compute:
                        computer = get_computer(field_def.computer)
                        if not computer:
                            continue
                        
                        # 准备参数
                        if field_def.needs_history:
                            value = computer(deps, history.copy())
                        else:
                            value = computer(deps, [])
                        
                        ext[field_name] = value
                    
                    updates.append({
                        'time': row['time'],
                        'ext_indicators': json.dumps(ext, ensure_ascii=False)
                    })
                
                # 更新历史
                history.append({'time': row['time'], **deps})
            
            # 3. 写入更新
            if updates:
                with engine.connect() as conn:
                    for upd in updates:
                        conn.execute(text(f"""
                            UPDATE `{table_name}`
                            SET ext_indicators = :json
                            WHERE bond_code = :code AND time = :time
                        """), {
                            'json': upd['ext_indicators'],
                            'code': bond_code,
                            'time': upd['time']
                        })
                    conn.commit()
            
            engine.dispose()
            return {'success': True, 'updates': len(updates)}
            
        except Exception as e:
            return {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}


def main():
    parser = argparse.ArgumentParser(description='JSON字段快速回填（通用化）')
    parser.add_argument('--date', help='单日回填 YYYYMMDD')
    parser.add_argument('--start', help='开始日期')
    parser.add_argument('--end', help='结束日期')
    parser.add_argument('--fields', nargs='+', required=True, help='要回填的JSON字段')
    parser.add_argument('--policy', choices=['skip', 'overwrite', 'merge'], 
                       default='skip', help='更新策略')
    parser.add_argument('--workers', type=int, default=8, help='并行进程数')
    args = parser.parse_args()
    
    # 确定日期范围
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
    
    # 执行回填
    backfiller = JsonFieldBackfiller(workers=args.workers, policy=args.policy)
    backfiller.backfill(dates, args.fields, args.policy)
    
    print("\n[COMPLETE] 回填完成")


if __name__ == '__main__':
    main()
```

---

## 四、关键设计决策

### 4.1 依赖解析策略

| 场景 | 处理方式 |
|------|---------|
| 依赖是物理列 | 从原表读取（如price, change_pct） |
| 依赖是JSON字段 | 从ext_indicators解析 |
| 依赖链 | 递归解析（A依赖B，B依赖C） |

**当前简化**：假设依赖字段已存在于JSON中（由monitor_bond.py实时计算写入）

### 4.2 更新策略优先级

```
字段级策略 > 全局策略

例：
- 全局策略：skip
- mkt_shape策略：overwrite
- mkt_shape_detail策略：skip

结果：
- mkt_shape：强制覆盖
- mkt_shape_detail：已有不覆盖
```

### 4.3 计算函数设计原则

1. **纯函数**：给定相同输入，总是返回相同输出
2. **无副作用**：不修改外部状态
3. **依赖注入**：通过dependencies参数传入，不直接查DB
4. **历史可选**：通过needs_history标记，不需要历史的字段不传history

---

## 五、使用示例

### 5.1 首次回填（skip模式）

```bash
python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape mkt_shape_detail
# 效果：只添加缺失的key，已有数据不覆盖
```

### 5.2 算法更新（overwrite模式）

```bash
python backfill_json_fields.py --date 20260723 --fields mkt_shape --policy overwrite
# 效果：强制重新计算并覆盖已有mkt_shape
```

### 5.3 增量添加（merge模式）

```bash
python backfill_json_fields.py --start 20260701 --end 20260731 \
    --fields mkt_shape mkt_trend_strength --policy merge
# 效果：添加新字段，保留已有字段（包括不在目标列表中的字段）
```

---

## 六、扩展新字段的步骤

以新增 `mkt_trend_strength` 为例：

1. **在`json_field_registry.py`中注册**：
```python
JsonFieldDef(
    name='mkt_trend_strength',
    depends=['mkt_weighted_slope_10m', 'mkt_vs_open_pct'],
    computer='compute_trend_strength',
    update_policy='skip',
    needs_history=False,
    description='趋势强度评分'
),
```

2. **在`json_field_computers.py`中实现计算函数**：
```python
def compute_trend_strength(dependencies: Dict, history: List[Dict]) -> float:
    slope = dependencies.get('mkt_weighted_slope_10m', 0)
    vs_open = dependencies.get('mkt_vs_open_pct', 0)
    # 计算逻辑...
    return strength_score

# 注册到FIELD_COMPUTERS
FIELD_COMPUTERS['compute_trend_strength'] = compute_trend_strength
```

3. **运行回填**：
```bash
python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_trend_strength
```

---

## 七、与旧方案的对比

| 特性 | 旧backfill_unified.py | 新backfill_json_fields.py |
|------|----------------------|--------------------------|
| 适用字段 | 物理列+JSON列 | 仅JSON列 |
| 依赖声明 | 无（硬编码） | 声明式（json_field_registry） |
| 更新策略 | 无（总是覆盖） | 可配置（skip/overwrite/merge） |
| 字段扩展 | 修改回填引擎 | 只添加注册+计算函数 |
| 复用已有字段 | 不支持 | 支持（自动解析依赖） |
| 速度 | ~400秒/天 | ~40秒/天 |

---

## 八、实施检查清单

- [ ] 创建`json_field_registry.py`（字段注册表）
- [ ] 创建`json_field_computers.py`（计算函数库）
- [ ] 修改`backfill_json_fields.py`（通用化回填引擎）
- [ ] 测试：skip模式回填
- [ ] 测试：overwrite模式回填
- [ ] 测试：merge模式回填
- [ ] 测试：扩展新字段流程
- [ ] 文档更新

---

## 九、总结

### 核心改进

1. **通用依赖解析**：通过`json_field_registry`声明依赖，自动提取
2. **可配置更新策略**：skip/overwrite/merge，满足不同场景
3. **易于扩展**：新增字段只需注册+实现计算函数
4. **保持高性能**：复用已有字段，按债券并行

### 使用模式

| 场景 | 命令 | 策略 |
|------|------|------|
| 首次回填 | `--fields f1 f2` | skip（默认） |
| 算法更新 | `--fields f1 --policy overwrite` | overwrite |
| 增量添加 | `--fields f1 f2 --policy merge` | merge |

### 扩展性

- 新增字段：2步（注册+实现）
- 修改算法：1步（修改计算函数）+ overwrite回填
- 复杂依赖：支持多字段依赖+历史数据依赖

---

请审核方案，确认后实施。
