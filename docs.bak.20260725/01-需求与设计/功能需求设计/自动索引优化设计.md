# 每日数据表自动索引优化方案

> 设计时间: 2026-03-31 13:56  
> 目标: 在每日更新 monitor_sssj 数据时自动添加索引

---

## 一、现状问题

### 1.1 表结构问题

**当前表结构**（无索引）:
```sql
CREATE TABLE monitor_gp_sssj_20260331 (
    time TIME,
    stock_code VARCHAR(10),
    short_name VARCHAR(20),
    price DECIMAL(10,2),
    change_pct DECIMAL(5,2),
    volume BIGINT,
    amount DECIMAL(15,2)
    -- 无任何索引！
);
```

**数据量**:
- 每3秒一个时间点
- 每天约 4800 个时间点
- 约 5000 只股票
- 总记录数: **2400万条/天**

### 1.2 慢查询问题

```sql
-- 按股票代码查询（27秒！）
SELECT * FROM monitor_gp_sssj_20260331 
WHERE stock_code = '300992' 
ORDER BY time ASC
-- 耗时: 26994ms (全表扫描)
```

---

## 二、优化方案设计

### 2.1 方案架构

```
每日数据更新流程:
    ↓
1. 创建新表（如果不存在）
    ↓
2. 插入第一批数据
    ↓
3. 【新增】自动添加索引
    ↓
4. 继续插入后续数据
    ↓
5. 数据更新完成
```

### 2.2 索引设计

**推荐索引**:
```sql
-- 主键索引（复合主键）
ALTER TABLE monitor_gp_sssj_20260331 
ADD PRIMARY KEY (stock_code, time);

-- 或分开的索引（如果主键冲突）
ALTER TABLE monitor_gp_sssj_20260331 
ADD INDEX idx_stock_time (stock_code, time);

-- 时间索引（用于时间范围查询）
ALTER TABLE monitor_gp_sssj_20260331 
ADD INDEX idx_time (time);
```

**索引效果**:
- 查询时间: 27秒 → 50-100ms (提升270-540倍)
- 写入性能: 略微下降（可接受）

---

## 三、实施方案

### 方案A: 在 save_dataframe 中添加索引（推荐）

**修改位置**: `redis_util.py` 中的 `save_dataframe` 函数

```python
def save_dataframe(
    df: pd.DataFrame,
    table_name: str,
    time_str: str,
    expire_seconds: int = 86400,
    use_compression: bool = False,
    auto_add_index: bool = True  # 新增参数
) -> bool:
    """
    保存 DataFrame 到 Redis，并自动添加数据库索引
    
    Args:
        ...
        auto_add_index: 是否自动添加索引（默认True）
    """
    # 1. 保存到 Redis（原有逻辑）
    # ...
    
    # 2. 【新增】检查并添加索引（只在第一次插入时）
    if auto_add_index and _should_add_index(table_name):
        _add_table_index(table_name)
    
    return True


# 记录已添加索引的表
_indexed_tables = set()

def _should_add_index(table_name: str) -> bool:
    """判断是否需要添加索引"""
    if table_name in _indexed_tables:
        return False
    
    # 检查是否已存在索引
    try:
        result = mysql_tool.execute(f"""
            SELECT COUNT(*) FROM information_schema.STATISTICS 
            WHERE table_schema = DATABASE() 
            AND table_name = '{table_name}' 
            AND index_name != 'PRIMARY'
        """)
        if result and result[0][0] > 0:
            _indexed_tables.add(table_name)
            return False
    except Exception:
        pass
    
    return True


def _add_table_index(table_name: str):
    """为表添加索引"""
    global _indexed_tables
    
    # 只处理 sssj 表
    if not ('_sssj_' in table_name or '_top30_' in table_name or '_apqd_' in table_name):
        return
    
    logger.info(f"正在为 {table_name} 添加索引...")
    
    try:
        # 根据表类型添加不同的索引
        if '_gp_sssj_' in table_name or '_zq_sssj_' in table_name or '_hy_sssj_' in table_name:
            # 实时数据表
            code_column = 'stock_code' if '_gp_' in table_name else ('bond_code' if '_zq_' in table_name else 'industry_code')
            
            # 添加复合索引
            mysql_tool.execute(f"""
                ALTER TABLE {table_name} 
                ADD INDEX idx_code_time ({code_column}, time)
            """)
            
            # 添加时间索引
            mysql_tool.execute(f"""
                ALTER TABLE {table_name} 
                ADD INDEX idx_time (time)
            """)
            
            logger.info(f"✓ {table_name} 索引添加成功")
            
        elif '_top30_' in table_name or '_apqd_' in table_name:
            # top30 和大盘强度表
            mysql_tool.execute(f"""
                ALTER TABLE {table_name} 
                ADD INDEX idx_time (time)
            """)
            
            logger.info(f"✓ {table_name} 索引添加成功")
        
        _indexed_tables.add(table_name)
        
    except Exception as e:
        logger.error(f"✗ {table_name} 索引添加失败: {e}")
```

---

### 方案B: 在 monitor_stock.py 中添加索引

**修改位置**: `monitor_stock.py` 中的 `process_all_stocks_once` 函数

```python
def process_all_stocks_once(loop_start: datetime):
    """
    处理一轮股票数据（含索引优化）
    """
    date_str = loop_start.strftime('%Y%m%d')
    time_full = loop_start.strftime("%H:%M:%S")
    
    # ... 获取数据 ...
    
    # 存储股票实时数据
    sssj_table = f"monitor_gp_sssj_{date_str}"
    save_dataframe(df_now, sssj_table, time_full, EXPIRE_SECONDS)
    
    # 【新增】如果是第一个时间点（09:30:00），添加索引
    if time_full == "09:30:00":
        add_index_to_sssj_tables(date_str)
    
    # ... 后续处理 ...


def add_index_to_sssj_tables(date_str: str):
    """
    为当天的 sssj 表添加索引
    
    在每天第一个时间点（09:30:00）调用
    """
    tables = [
        (f'monitor_gp_sssj_{date_str}', 'stock_code'),
        (f'monitor_zq_sssj_{date_str}', 'bond_code'),
        (f'monitor_hy_sssj_{date_str}', 'industry_code'),
        (f'monitor_gp_top30_{date_str}', None),
        (f'monitor_zq_top30_{date_str}', None),
        (f'monitor_hy_top30_{date_str}', None),
        (f'monitor_gp_apqd_{date_str}', None),
    ]
    
    for table, code_column in tables:
        try:
            # 检查表是否存在
            result = mysql_tool.execute(f"""
                SELECT COUNT(*) FROM information_schema.TABLES 
                WHERE table_schema = DATABASE() AND table_name = '{table}'
            """)
            if not result or result[0][0] == 0:
                continue
            
            # 检查是否已有索引
            result = mysql_tool.execute(f"""
                SELECT COUNT(*) FROM information_schema.STATISTICS 
                WHERE table_schema = DATABASE() 
                AND table_name = '{table}' 
                AND index_name != 'PRIMARY'
            """)
            if result and result[0][0] > 0:
                logger.info(f"{table} 已有索引，跳过")
                continue
            
            # 添加索引
            if code_column:
                # 实时数据表：添加复合索引
                mysql_tool.execute(f"""
                    ALTER TABLE {table} 
                    ADD INDEX idx_code_time ({code_column}, time)
                """)
            
            # 所有表都添加时间索引
            mysql_tool.execute(f"""
                ALTER TABLE {table} 
                ADD INDEX idx_time (time)
            """)
            
            logger.info(f"✓ {table} 索引添加成功")
            
        except Exception as e:
            logger.error(f"✗ {table} 索引添加失败: {e}")
```

---

### 方案C: 独立索引管理模块（最灵活）

**新增文件**: `src/gs2026/monitor/table_index_manager.py`

```python
"""
表索引管理模块
自动为监控数据表添加索引
"""
from datetime import datetime
from typing import List, Tuple
from loguru import logger

from gs2026.utils import mysql_util

mysql_tool = mysql_util.MysqlTool()

# 表索引配置
INDEX_CONFIG = {
    # 实时数据表
    'monitor_gp_sssj_{date}': {
        'code_column': 'stock_code',
        'indexes': [
            ('idx_code_time', 'stock_code, time'),
            ('idx_time', 'time'),
        ]
    },
    'monitor_zq_sssj_{date}': {
        'code_column': 'bond_code',
        'indexes': [
            ('idx_code_time', 'bond_code, time'),
            ('idx_time', 'time'),
        ]
    },
    'monitor_hy_sssj_{date}': {
        'code_column': 'industry_code',
        'indexes': [
            ('idx_code_time', 'industry_code, time'),
            ('idx_time', 'time'),
        ]
    },
    # Top30表
    'monitor_gp_top30_{date}': {
        'indexes': [('idx_time', 'time')]
    },
    'monitor_zq_top30_{date}': {
        'indexes': [('idx_time', 'time')]
    },
    'monitor_hy_top30_{date}': {
        'indexes': [('idx_time', 'time')]
    },
    # 大盘强度表
    'monitor_gp_apqd_{date}': {
        'indexes': [('idx_time', 'time')]
    },
}


class TableIndexManager:
    """表索引管理器"""
    
    _indexed_tables = set()  # 已添加索引的表
    
    @classmethod
    def add_index_for_date(cls, date_str: str = None):
        """
        为指定日期的所有监控表添加索引
        
        Args:
            date_str: 日期 YYYYMMDD，默认今天
        """
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')
        
        logger.info(f"开始为 {date_str} 的监控表添加索引...")
        
        for table_pattern, config in INDEX_CONFIG.items():
            table_name = table_pattern.format(date=date_str)
            cls._add_index_to_table(table_name, config)
        
        logger.info(f"{date_str} 索引添加完成")
    
    @classmethod
    def _add_index_to_table(cls, table_name: str, config: dict):
        """为单个表添加索引"""
        if table_name in cls._indexed_tables:
            return
        
        try:
            # 检查表是否存在
            result = mysql_tool.execute(f"""
                SELECT COUNT(*) FROM information_schema.TABLES 
                WHERE table_schema = DATABASE() AND table_name = '{table_name}'
            """)
            if not result or result[0][0] == 0:
                return
            
            # 获取已有索引
            result = mysql_tool.execute(f"""
                SELECT index_name FROM information_schema.STATISTICS 
                WHERE table_schema = DATABASE() 
                AND table_name = '{table_name}'
            """)
            existing_indexes = {row[0] for row in result} if result else set()
            
            # 添加配置的索引
            for index_name, columns in config.get('indexes', []):
                if index_name in existing_indexes:
                    continue
                
                mysql_tool.execute(f"""
                    ALTER TABLE {table_name} 
                    ADD INDEX {index_name} ({columns})
                """)
                logger.info(f"✓ {table_name}.{index_name} 创建成功")
            
            cls._indexed_tables.add(table_name)
            
        except Exception as e:
            logger.error(f"✗ {table_name} 索引添加失败: {e}")
    
    @classmethod
    def should_add_index(cls, table_name: str) -> bool:
        """判断是否需要添加索引"""
        if table_name in cls._indexed_tables:
            return False
        
        # 检查是否是监控表
        for pattern in INDEX_CONFIG.keys():
            if '{date}' in pattern:
                prefix = pattern.split('{date}')[0]
                if table_name.startswith(prefix):
                    return True
        
        return False


# 便捷函数
def auto_add_index(table_name: str):
    """
    自动为表添加索引（如果符合配置）
    
    在 save_dataframe 等函数中调用
    """
    if not TableIndexManager.should_add_index(table_name):
        return
    
    # 提取日期
    for pattern in INDEX_CONFIG.keys():
        prefix = pattern.split('{date}')[0]
        if table_name.startswith(prefix):
            date_str = table_name[len(prefix):]
            TableIndexManager.add_index_for_date(date_str)
            break
```

**在 monitor_stock.py 中使用**:
```python
from gs2026.monitor.table_index_manager import TableIndexManager, auto_add_index

# 方式1: 每天开盘时调用
def process_all_stocks_once(loop_start: datetime):
    time_full = loop_start.strftime("%H:%M:%S")
    
    # 09:30:00 第一次运行时添加索引
    if time_full == "09:30:00":
        TableIndexManager.add_index_for_date()
    
    # ... 后续逻辑

# 方式2: 在 save_dataframe 中自动检测
save_dataframe(df, table_name, time_str)
auto_add_index(table_name)  # 自动添加索引
```

---

## 四、推荐方案

### 推荐: 方案C（独立索引管理模块）

**理由**:
1. **职责分离**: 索引逻辑独立，不影响核心业务
2. **可配置**: 通过配置管理不同表的索引
3. **可复用**: 可在多个地方调用（save_dataframe、定时任务等）
4. **可扩展**: 易于添加新表类型

---

## 五、实施计划

| 阶段 | 时间 | 内容 |
|------|------|------|
| 阶段1 | 30分钟 | 创建 table_index_manager.py |
| 阶段2 | 15分钟 | 在 monitor_stock.py 中集成 |
| 阶段3 | 15分钟 | 测试索引添加功能 |
| **总计** | **60分钟** | |

---

## 六、预期效果

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 单股票查询 | 27s | 50-100ms | 270-540x |
| API响应 | 700ms | 200ms | 3.5x |
| 索引添加时间 | - | <30秒 | 一次性 |

---

**文档位置**: `docs/auto_index_optimization_design.md`

**请确认方案后实施。**
