# 快速回填方案设计 - 针对JSON扩展字段优化

## 一、当前回填方案分析

### 1.1 当前流程

```
backfill_unified.py 流程：
1. 读取单日数据（所有债券，所有tick）
2. 逐tick计算字段（依赖历史状态）
3. 批量UPDATE写入结果
4. 重复1-3直到所有日期完成
```

### 1.2 性能瓶颈

| 瓶颈 | 原因 | 影响 |
|------|------|------|
| **逐tick计算** | 需要维护历史状态（deque） | 无法并行，CPU密集 |
| **全表读取** | 每次都要读取所有列 | IO密集 |
| **批量UPDATE** | 临时表+JOIN，事务开销 | 写入延迟 |
| **单日串行** | 状态无法跨日共享 | 无法并行多日 |

### 1.3 当前性能

- 单日数据：~15万行（145只债券 × ~1000 ticks）
- 当前速度：~400秒/天（34天需要4小时）
- 主要耗时：逐tick计算（70%）+ 批量写入（30%）

---

## 二、问题分析：JSON扩展字段的特殊性

### 2.1 JSON字段特点

**存储方式**：
```sql
ext_indicators: '{"mkt_vs_open_pct": 0.5, "mkt_shape": "单边上行", ...}'
```

**特点**：
- 所有扩展字段打包在一个JSON字符串中
- 新增字段 = 在JSON中增加key-value
- 不需要ALTER TABLE添加列

### 2.2 当前回填JSON字段的问题

**问题1：重复计算**
- 回填`mkt_shape`时，需要重新计算所有tick的历史状态
- 但`mkt_vs_open_pct`等字段已经存在，不需要重算

**问题2：无法增量更新JSON**
- 当前方案：读取整行 → 计算新字段 → 更新整行
- 理想方案：只更新JSON中的新增字段

**问题3：状态依赖**
- `mkt_shape`需要历史数据（_mkt_shape_history）
- 无法从中间tick开始计算

---

## 三、最优方案设计

### 方案A：JSON字段专用快速回填（推荐）

**核心思想**：
1. JSON字段独立回填（不依赖物理列）
2. 利用已有字段避免重复计算
3. 流式处理，低内存占用

#### 3.1 方案架构

```python
# 新增脚本：backfill_json_fields.py

class JsonFieldBackfiller:
    """JSON扩展字段快速回填器"""
    
    def backfill(self, date_range, json_fields):
        """
        快速回填JSON字段
        
        特点：
        - 只读取ext_indicators列（不读其他列）
        - 解析已有JSON，复用已有字段
        - 只计算新增字段
        - 流式UPDATE（单条UPDATE JSON字段）
        """
        for date in date_range:
            self._backfill_single_day(date, json_fields)
    
    def _backfill_single_day(self, date, json_fields):
        """单日回填"""
        # 1. 流式读取（只读bond_code, time, ext_indicators）
        # 2. 按债券分组（每只债券独立计算历史状态）
        # 3. 逐tick计算新增字段
        # 4. 更新JSON（只UPDATE ext_indicators列）
```

#### 3.2 关键优化点

**优化1：最小化读取**
```python
# 只读取需要的列
SELECT bond_code, time, ext_indicators FROM table
# 不读取price, change_pct等物理列
```

**优化2：复用已有JSON字段**
```python
# 解析已有JSON
existing = json.loads(row['ext_indicators'])

# 复用已有字段，避免重复计算
mkt_vs_open_pct = existing.get('mkt_vs_open_pct')  # 直接用，不重新算

# 只计算新增字段
if 'mkt_shape' not in existing:
    mkt_shape = self._calc_shape(history)
    existing['mkt_shape'] = mkt_shape
```

**优化3：单条流式UPDATE**
```python
# 不创建临时表，直接单条UPDATE
UPDATE table SET ext_indicators = :new_json 
WHERE bond_code = :code AND time = :time

# 优点：
# - 无需临时表创建/删除开销
# - 事务粒度小，不锁表
# - 内存占用低（不需要攒批）
```

**优化4：按债券并行**
```python
# 每只债券独立计算（无状态依赖）
# 可以按债券并行，而非按日期并行

with Pool(workers) as pool:
    pool.map(process_bond, all_bonds)
```

#### 3.3 性能预估

| 优化点 | 效果 |
|--------|------|
| 最小化读取 | -50% IO |
| 复用已有字段 | -70% 计算（大部分字段已存在） |
| 单条流式UPDATE | -30% 写入开销 |
| 按债券并行 | -80% 时间（假设8核） |
| **综合** | **~10x 提速**（400秒 → 40秒/天） |

### 方案B：预计算+缓存（更激进）

**核心思想**：
- 历史数据不变，预计算所有字段存入缓存
- 回填时直接复制缓存结果

```python
# 预计算缓存（每日收盘后）
class DailyCache:
    def compute_and_cache(self, date):
        """收盘后预计算所有字段，存入缓存表"""
        # 计算所有字段
        # 存入 cache_table (date, bond_code, time, all_fields_json)

# 回填时直接复制
class FastBackfill:
    def backfill_from_cache(self, date, fields):
        """从缓存复制字段"""
        # INSERT INTO real_table SELECT ... FROM cache_table
```

**优点**：回填 = 纯SQL复制，极快（<10秒/天）
**缺点**：需要预计算基础设施，占用额外存储

---

## 四、实施方案（方案A）

### 4.1 新增文件

**`scripts/backfill_json_fields.py`** - JSON字段快速回填脚本

```python
#!/usr/bin/env python3
"""
JSON扩展字段快速回填脚本

特点：
- 只读取ext_indicators列，最小化IO
- 复用已有JSON字段，避免重复计算
- 按债券并行，最大化CPU利用
- 流式单条UPDATE，低内存占用

用法：
    python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape mkt_shape_detail
    python backfill_json_fields.py --date 20260723 --fields mkt_shape
"""

import argparse
import json
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import List, Set, Dict

import pandas as pd
from sqlalchemy import create_engine, text

# 添加src到path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from gs2026.utils import config_util


DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
TABLE_PREFIX = "monitor_zq_sssj_"


class JsonFieldBackfiller:
    """JSON字段快速回填器"""
    
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
    
    def backfill(self, dates: List[str], fields: List[str]):
        """批量回填多日期"""
        print(f"[BACKFILL] 回填 {len(dates)} 天, 字段: {fields}")
        
        for date_str in dates:
            self._backfill_single_day(date_str, fields)
    
    def _backfill_single_day(self, date_str: str, fields: List[str]):
        """单日回填"""
        table_name = f"{TABLE_PREFIX}{date_str}"
        print(f"\n[{date_str}] 开始回填...")
        t0 = time.time()
        
        # 1. 获取所有债券代码
        bonds = self._get_bonds(table_name)
        if not bonds:
            print(f"  [SKIP] 无数据")
            return
        
        print(f"  [INFO] {len(bonds)} 只债券需要处理")
        
        # 2. 按债券并行处理
        completed = 0
        failed = 0
        
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._process_bond, date_str, bond_code, fields): bond_code 
                for bond_code in bonds
            }
            
            for future in as_completed(futures):
                bond_code = futures[future]
                try:
                    result = future.result()
                    if result:
                        completed += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"  [ERROR] {bond_code}: {e}")
                    failed += 1
                
                if (completed + failed) % 10 == 0:
                    print(f"  [PROGRESS] {completed + failed}/{len(bonds)} 完成")
        
        elapsed = time.time() - t0
        print(f"  [DONE] 完成: {completed} 成功, {failed} 失败, 耗时 {elapsed:.1f}s")
    
    def _get_bonds(self, table_name: str) -> List[str]:
        """获取所有债券代码"""
        with self.engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT DISTINCT bond_code FROM `{table_name}`
                WHERE ext_indicators IS NOT NULL
            """))
            return [row[0] for row in result]
    
    def _process_bond(self, date_str: str, bond_code: str, fields: List[str]) -> bool:
        """处理单只债券（独立进程）"""
        try:
            # 每个进程创建独立引擎
            engine = self._create_engine()
            table_name = f"{TABLE_PREFIX}{date_str}"
            
            # 1. 读取该债券的所有数据（只读ext_indicators）
            with engine.connect() as conn:
                df = pd.read_sql(text(f"""
                    SELECT time, ext_indicators 
                    FROM `{table_name}`
                    WHERE bond_code = :code
                    ORDER BY time
                """), conn, params={'code': bond_code})
            
            if df.empty:
                return True
            
            # 2. 解析并检查需要计算的字段
            updates = []
            history = []  # 用于计算状态依赖字段
            
            for _, row in df.iterrows():
                ext_json = row['ext_indicators']
                if not ext_json:
                    continue
                
                try:
                    ext = json.loads(ext_json)
                except:
                    ext = {}
                
                # 检查是否需要计算新字段
                need_update = False
                for field in fields:
                    if field not in ext:
                        need_update = True
                        break
                
                if not need_update:
                    # 复用已有字段维护history
                    vs_open = ext.get('mkt_vs_open_pct', 0)
                    history.append({
                        'time': row['time'],
                        'vs_open': vs_open
                    })
                    continue
                
                # 需要计算新字段
                new_values = self._compute_fields(history, ext, fields)
                if new_values:
                    ext.update(new_values)
                    updates.append({
                        'time': row['time'],
                        'ext_indicators': json.dumps(ext, ensure_ascii=False)
                    })
                
                # 更新history
                vs_open = ext.get('mkt_vs_open_pct', 0)
                history.append({
                    'time': row['time'],
                    'vs_open': vs_open
                })
            
            # 3. 批量UPDATE
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
            return True
            
        except Exception as e:
            print(f"  [ERROR] {bond_code}: {e}")
            return False
    
    def _compute_fields(self, history: List[Dict], ext: Dict, fields: List[str]) -> Dict:
        """计算新字段（复用已有字段）"""
        result = {}
        
        # 获取已有字段
        vs_open = ext.get('mkt_vs_open_pct')
        if vs_open is None and history:
            vs_open = history[-1]['vs_open']
        
        # 计算mkt_shape
        if 'mkt_shape' in fields:
            shape, detail = self._calc_shape(history + [{'vs_open': vs_open}])
            result['mkt_shape'] = shape
            if 'mkt_shape_detail' in fields:
                result['mkt_shape_detail'] = detail
        
        return result
    
    def _calc_shape(self, history: List[Dict]) -> tuple:
        """计算大盘形态（简化版）"""
        if len(history) < 10:
            return '横盘', '数据不足'
        
        vs_values = [h['vs_open'] for h in history]
        cur = vs_values[-1]
        high = max(vs_values)
        low = min(vs_values)
        range_val = high - low
        
        if range_val < 0.5:
            return '横盘', f'振幅{range_val:.2f}%<0.5%'
        
        n = len(vs_values)
        high_idx = vs_values.index(high)
        low_idx = vs_values.index(low)
        high_pos = high_idx / (n - 1)
        low_pos = low_idx / (n - 1)
        
        sig = range_val * 0.5
        recovery = cur - low
        drawdown = high - cur
        
        if low_pos < 0.2 and cur > 0 and drawdown < sig:
            return '单边上行', f'开盘即最低'
        if high_pos < 0.2 and cur < 0 and recovery < sig:
            return '单边下行', f'开盘即最高'
        if low_pos > 0.2 and recovery > sig and cur > 0:
            return '低开高走', f'回升{recovery:.2f}%'
        if high_pos > 0.2 and drawdown > sig and cur < 0:
            return '高开低走', f'回落{drawdown:.2f}%'
        
        return '横盘', '无明确形态'


def main():
    parser = argparse.ArgumentParser(description='JSON字段快速回填')
    parser.add_argument('--date', help='单日回填 YYYYMMDD')
    parser.add_argument('--start', help='开始日期')
    parser.add_argument('--end', help='结束日期')
    parser.add_argument('--fields', nargs='+', required=True, help='要回填的JSON字段')
    parser.add_argument('--workers', type=int, default=8, help='并行进程数')
    args = parser.parse_args()
    
    # 确定日期范围
    if args.date:
        dates = [args.date]
    elif args.start and args.end:
        # 获取交易日列表
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
    backfiller = JsonFieldBackfiller(workers=args.workers)
    backfiller.backfill(dates, args.fields)
    
    print("\n[COMPLETE] 回填完成")


if __name__ == '__main__':
    main()
```

### 4.2 与现有回填方案对比

| 特性 | 现有backfill_unified.py | 新增backfill_json_fields.py |
|------|------------------------|----------------------------|
| 适用字段 | 物理列+JSON列 | 仅JSON列 |
| 读取列 | 所有依赖列 | 仅ext_indicators |
| 计算方式 | 逐tick全量计算 | 复用已有字段，增量计算 |
| 并行粒度 | 按日期 | 按债券 |
| 内存占用 | 高（临时表） | 低（流式） |
| 适用场景 | 物理列回填、算法更新 | JSON字段新增 |
| 速度 | ~400秒/天 | ~40秒/天（预估10x） |

### 4.3 使用方式

```bash
# 新增JSON字段快速回填
python scripts/backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape mkt_shape_detail

# 单日回填
python scripts/backfill_json_fields.py --date 20260723 --fields mkt_shape

# 物理列或全量重算（用旧脚本）
python scripts/backfill_unified.py --start 20260701 --end 20260731 --fields slope_short --force
```

---

## 五、总结

### 核心改进

| 问题 | 解决方案 | 效果 |
|------|---------|------|
| 逐tick计算慢 | 复用已有JSON字段 | -70%计算 |
| 全表读取IO大 | 只读ext_indicators | -50% IO |
| 临时表开销 | 单条流式UPDATE | -30%写入 |
| 单日串行 | 按债券并行 | -80%时间 |
| **综合** | **JSON字段专用回填** | **~10x提速** |

### 两套方案分工

| 场景 | 使用脚本 | 原因 |
|------|---------|------|
| 新增JSON字段 | `backfill_json_fields.py` | 快速，复用已有数据 |
| 物理列回填 | `backfill_unified.py` | 需要逐tick计算 |
| 算法更新重算 | `backfill_unified.py --force` | 需要全量重算 |
| 新增物理列 | `backfill_unified.py` | 需要ALTER TABLE |

### 实施建议

1. **保留现有backfill_unified.py**（物理列+全量重算）
2. **新增backfill_json_fields.py**（JSON字段快速回填）
3. **文档说明两套方案的使用场景**

---

请审核方案，确认后实施。
