"""
统一字段回填引擎 - 主入口脚本 (优化版 v2.2)
支持多进程并行 + 批量UPDATE + 代码配置模式 + 交易日期自动过滤

用法:
    # 方式1: 命令行参数模式
    python scripts/backfill_unified.py --start 20260701 --end 20260731
    
    # 方式2: 代码配置模式（修改 DEFAULT_CONFIG 后运行）
    python scripts/backfill_unified.py

命令行参数:
    --date 20260710              单日回填
    --start 20260701 --end 20260731  日期范围（自动过滤为交易日）
    --fields field1 field2       指定字段
    --skip-existing              跳过已有字段（与--force配合使用）
    --force                      强制重算并覆盖（默认True）
    --workers 8                  并行进程数

参数组合说明（按优先级排序）:
    
    【组合1】--force（最高优先级，默认启用）
    效果: 强制重算所有字段，覆盖已有数据
    用途: 算法更新后、确保数据一致性
    注意: --skip-existing 在此模式下被忽略
    示例: python backfill_unified.py --start 20260701 --end 20260731 --force
    
    【组合2】--force=False（即不指定--force）
    此时根据 --skip-existing 判断:
    
    ├─ --skip-existing=False（默认）
    │  效果: 计算所有字段，可能覆盖已有数据
    │  用途: 首次回填、需要更新特定字段
    │  示例: python backfill_unified.py --start 20260701 --end 20260731
    │
    └─ --skip-existing=True
       效果: 只计算表中不存在的字段（增量回填）
       用途: 补充新字段、续跑中断任务（推荐日常使用）
       示例: python backfill_unified.py --start 20260701 --end 20260731 --skip-existing

代码配置:
    修改脚本底部的 DEFAULT_CONFIG 字典，设置 USE_DEFAULT_CONFIG = True
    默认: force=True, skip_existing=False（全量重算并覆盖）

详细说明:
    【交易日期过滤】
    输入的日期范围会自动过滤为实际交易日（从 data_jyrl 表查询）
    非交易日（周末、节假日）会自动跳过，无需手动排除
    
    【并行进程数计算】
    默认: workers = min(CPU核数-1, 8, 日期数)
    说明: 保留1核给系统、最多8进程、不超过日期数
    手动指定: --workers 4 可覆盖自动计算
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text, inspect

# 添加 scripts 目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from field_registry import FIELD_REGISTRY, get_field_names, get_field_def, get_all_depends, get_categories
from compute_engine import ComputeEngine


# ========== 默认配置（代码修改模式） ==========
# 当 USE_DEFAULT_CONFIG = True 时，使用以下配置，忽略命令行参数
USE_DEFAULT_CONFIG = True

DEFAULT_CONFIG = {
    'mode': 'range',           # 'single' 或 'range'
    'date': '20260605',        # mode='single' 时使用
    'start': '20260608',       # mode='range' 时使用
    'end': '20260811',         # mode='range' 时使
    'fields': None,            # None=全部字段，或 ['field1', 'field2']
    'skip_existing': False,    # True=跳过已有字段，False=计算所有字段
    'force': True,             # True=强制覆盖已有数据，False=根据skip_existing判断
    'workers': 4,           # None=自动计算，或指定数字如 4, 8
    'dry_run': False,          # True=试运行（只显示计划不执行）
    
    # 【参数组合说明 - 按优先级排序】
    # 
    # 组合1: force=True（最高优先级，skip_existing被忽略）
    #   效果: 强制重算所有字段，覆盖已有数据
    #   用途: 算法更新后需要重新计算、怀疑数据有问题
    #   风险: 会覆盖已有数据，谨慎使用
    # 
    # 组合2: force=False + skip_existing=False
    #   效果: 计算所有指定字段，写入所有结果（可能覆盖）
    #   用途: 首次回填、需要更新特定字段
    #   注意: 不特意跳过已有数据，但也不会强制清空再写入
    # 
    # 组合3: force=False + skip_existing=True（推荐日常使用）
    #   效果: 只计算表中不存在的字段（增量回填）
    #   用途: 补充新字段、续跑中断的任务
    #   优点: 最快，不碰已有数据
    # 
    # 【默认值说明】
    # 默认: force=True（全量重算并覆盖）
    # 原因: 确保数据一致性，避免新旧算法混合导致的数据不一致
    # 建议: 日常增量回填时手动改为 force=False, skip_existing=True
}


# ========== 运行时配置（命令行或代码配置） ==========
DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
TABLE_PREFIX = "monitor_zq_sssj_"
BATCH_SIZE = 2000  # 每批UPDATE行数
CODE_COL = 'bond_code'  # 主键列名


def create_db_engine(db_url=None, pool_size=5):
    """
    创建优化的数据库引擎
    【优化】增加超时参数，避免MySQL超时断开
    """
    url = db_url or DB_URL
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=pool_size * 2,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
        connect_args={
            'connect_timeout': 60,      # 【优化】连接超时60秒
            'read_timeout': 600,         # 【优化】读取超时10分钟
            'write_timeout': 600,        # 【优化】写入超时10分钟
        },
        execution_options={
            'isolation_level': 'READ_COMMITTED',  # 【优化】降低锁竞争
        }
    )


# ========== Schema管理 ==========
class SchemaManager:
    """表结构管理器：检测缺失字段并自动添加"""

    def __init__(self, engine):
        self.engine = engine

    def get_existing_columns(self, table_name: str) -> set:
        """获取表的现有列名集合"""
        try:
            insp = inspect(self.engine)
            if not insp.has_table(table_name):
                return set()
            columns = insp.get_columns(table_name)
            return {col['name'] for col in columns}
        except Exception as e:
            print(f"  [ERROR] 无法检查表结构 {table_name}: {e}")
            return set()

    def ensure_columns(self, table_name: str, fields_to_add: list) -> list:
        """
        确保表中存在指定字段，不存在则 ALTER TABLE ADD COLUMN
        【修复】如果ext_indicators列存在但类型不是TEXT，自动修复
        Returns:
            实际添加的列名列表
        """
        existing = self.get_existing_columns(table_name)
        if not existing:
            print(f"  [WARN] 表 {table_name} 不存在或无法访问")
            return []

        added = []
        with self.engine.connect() as conn:
            for field_def in fields_to_add:
                if field_def.name not in existing:
                    col_type = self._map_db_type(field_def.db_type)
                    sql = f"ALTER TABLE `{table_name}` ADD COLUMN `{field_def.name}` {col_type} DEFAULT NULL"
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        added.append(field_def.name)
                        print(f"  [ALTER] 添加列 {field_def.name} ({col_type})")
                    except Exception as e:
                        if 'Duplicate column' in str(e):
                            pass
                        else:
                            print(f"  [ERROR] 添加列 {field_def.name} 失败: {e}")
                            conn.rollback()
        return added

    def _map_db_type(self, db_type: str) -> str:
        """映射字段类型到MySQL类型"""
        type_map = {
            'FLOAT': 'FLOAT',
            'INT': 'INT',
            'JSON': 'JSON',
            'VARCHAR': 'VARCHAR(255)',
            'TEXT': 'TEXT',
        }
        return type_map.get(db_type.upper(), db_type)


# ========== 批量写入器（优化版） ==========
class BatchWriter:
    """批量结果写入器 - 使用临时表+UPDATE JOIN实现真正批量"""

    def __init__(self, engine, table_name, batch_size=1000):
        self.engine = engine
        self.table_name = table_name
        self.batch_size = batch_size
        self.total_updated = 0
        self.total_batches = 0

    def write_results(self, all_results: list, fields: list):
        """
        批量写入结果 - 使用临时表+UPDATE JOIN
        比逐行UPDATE快 10-50x
        """
        if not all_results:
            print(f"  [SKIP] 无结果需要写入")
            return

        import pandas as pd

        # 转换为DataFrame
        df = pd.DataFrame(all_results)

        # 只保留需要的字段
        keep_cols = ['bond_code', 'time'] + [f for f in fields if f in df.columns]
        df = df[[c for c in keep_cols if c in df.columns]]

        if df.empty:
            print(f"  [SKIP] 无有效数据")
            return

        print(f"  [WRITE] 批量写入 {len(df)} 行, {len(fields)} 个字段 ...")
        t0 = time.time()

        # 使用临时表+UPDATE JOIN
        self._bulk_update_via_temp_table(df, fields)

        elapsed = time.time() - t0
        print(f"  [WRITE] 写入完成: {self.total_updated} 行更新, 耗时 {elapsed:.1f}s")

    def _bulk_update_via_temp_table(self, df: pd.DataFrame, fields: list):
        """
        使用临时表+UPDATE JOIN实现批量更新
        
        实现方式：创建普通临时表（非TEMPORARY），使用pandas to_sql批量插入，然后UPDATE JOIN
        使用普通表确保to_sql的engine连接可以访问
        """
        from sqlalchemy import text
        import pandas as pd

        # 使用普通表（带唯一前缀），确保跨连接可见
        temp_table = f"_temp_backfill_{int(time.time() * 1000)}"

        try:
            # 1. 创建临时表（使用普通表，非TEMPORARY，确保to_sql可以访问）
            # 根据字段类型定义列（JSON字段用TEXT，其他用FLOAT）
            field_col_defs = []
            json_fields = set()
            for f in fields:
                fdef = get_field_def(f)
                if fdef and fdef.db_type == 'JSON':
                    field_col_defs.append(f'`{f}` TEXT')
                    json_fields.add(f)
                else:
                    field_col_defs.append(f'`{f}` FLOAT')
            field_defs = ', '.join(field_col_defs)
            create_sql = f"""
                CREATE TABLE `{temp_table}` (
                    bond_code VARCHAR(20),
                    time VARCHAR(20),
                    {field_defs},
                    PRIMARY KEY (bond_code, time)
                ) ENGINE=InnoDB
            """
            with self.engine.connect() as conn:
                conn.execute(text(create_sql))
                conn.commit()

            # 2. 准备数据
            # 只保留需要的列（确保列存在）
            available_cols = ['bond_code', 'time']
            for f in fields:
                if f in df.columns:
                    available_cols.append(f)
                else:
                    print(f"    [WARN] 字段 {f} 在结果中不存在，跳过")
            
            if len(available_cols) <= 2:
                print(f"    [SKIP] 无有效字段需要写入")
                return
            
            insert_df = df[available_cols].copy()
            
            # 去重：保留每个(bond_code, time)组合的最后一条记录
            insert_df = insert_df.drop_duplicates(subset=['bond_code', 'time'], keep='last')
            
            # 确保数值类型正确（跳过JSON/TEXT字段）
            for col in insert_df.columns:
                if col not in ['bond_code', 'time'] and col not in json_fields:
                    insert_df[col] = pd.to_numeric(insert_df[col], errors='coerce')
            
            # 3. 使用pandas to_sql批量插入
            print(f"    [INSERT] 使用pandas to_sql插入 {len(insert_df)} 行到临时表...")
            insert_df.to_sql(
                name=temp_table,
                con=self.engine,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
            print(f"    [INSERT] 临时表写入完成")

            # 4. 【优化】分批UPDATE JOIN（避免单条SQL过大导致超时）
            actual_fields = [f for f in fields if f in df.columns]
            if not actual_fields:
                print(f"    [SKIP] 无有效字段需要更新")
                return
            
            # 分批更新：每批1000行
            BATCH_SIZE = 1000
            total_updated = 0
            total_rows = len(insert_df)
            
            for batch_start in range(0, total_rows, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_rows)
                batch_df = insert_df.iloc[batch_start:batch_end]
                
                # 创建批次临时表
                batch_temp_table = f"{temp_table}_batch_{batch_start}"
                
                try:
                    # 删除旧批次表
                    with self.engine.connect() as conn:
                        conn.execute(text(f"DROP TABLE IF EXISTS `{batch_temp_table}`"))
                        conn.commit()
                    
                    # 插入批次数据
                    batch_df.to_sql(
                        name=batch_temp_table,
                        con=self.engine,
                        if_exists='replace',
                        index=False,
                        method='multi',
                        chunksize=500
                    )
                    
                    # 执行批次UPDATE
                    set_clauses = ', '.join([f't.`{f}` = s.`{f}`' for f in actual_fields])
                    update_sql = f"""
                        UPDATE `{self.table_name}` t
                        INNER JOIN `{batch_temp_table}` s ON t.bond_code = s.bond_code AND t.time = s.time
                        SET {set_clauses}
                    """
                    
                    with self.engine.connect() as conn:
                        result = conn.execute(text(update_sql))
                        conn.commit()
                        batch_updated = result.rowcount
                        total_updated += batch_updated
                    
                    # 清理批次临时表
                    with self.engine.connect() as conn:
                        conn.execute(text(f"DROP TABLE IF EXISTS `{batch_temp_table}`"))
                        conn.commit()
                    
                    print(f"    [BATCH] 批次 {batch_start//BATCH_SIZE + 1}/{(total_rows-1)//BATCH_SIZE + 1}: "
                          f"更新 {batch_updated} 行 ({batch_start+1}-{batch_end})")
                    
                except Exception as e:
                    print(f"    [ERROR] 批次更新失败 {batch_start}-{batch_end}: {e}")
                    # 尝试清理批次表
                    try:
                        with self.engine.connect() as conn:
                            conn.execute(text(f"DROP TABLE IF EXISTS `{batch_temp_table}`"))
                            conn.commit()
                    except:
                        pass
                    raise
            
            self.total_updated = total_updated
            self.total_batches = (total_rows - 1) // BATCH_SIZE + 1
            print(f"    [BULK] 分批UPDATE完成: 共{self.total_batches}批, 更新{self.total_updated}行 ({len(actual_fields)}个字段)")

        finally:
            # 【优化】清理临时表（使用新连接，避免超时连接问题）
            try:
                # 创建新引擎专门用于清理，避免使用可能已超时的连接
                from sqlalchemy import create_engine
                cleanup_engine = create_engine(
                    self.engine.url,
                    pool_size=1,
                    max_overflow=0,
                    pool_recycle=60,
                    connect_args={
                        'connect_timeout': 30,      # 【优化】增加超时
                        'read_timeout': 60,          # 【优化】增加超时
                        'write_timeout': 60,         # 【优化】增加超时
                    }
                )
                with cleanup_engine.connect() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS `{temp_table}`"))
                    conn.commit()
                cleanup_engine.dispose()
                print(f"    [CLEANUP] 临时表 {temp_table} 已清理")
            except Exception as e:
                print(f"    [WARN] 清理临时表失败（可忽略）: {e}")


# ========== 数据加载 ==========
def load_table_data(engine, table_name: str, needed_columns: set) -> pd.DataFrame:
    """
    加载表数据（全表读入，按时间排序）
    【注意】此函数会一次性加载所有数据到内存，大数据量时可能OOM
    如需流式读取，请使用 load_table_data_streaming
    """
    insp = inspect(engine)
    if not insp.has_table(table_name):
        return pd.DataFrame()

    actual_cols = {col['name'] for col in insp.get_columns(table_name)}
    select_cols = sorted(needed_columns & actual_cols)

    if not select_cols:
        return pd.DataFrame()

    for pk in [CODE_COL, 'time']:
        if pk in actual_cols and pk not in select_cols:
            select_cols.append(pk)

    cols_str = ", ".join([f"`{c}`" for c in select_cols])
    sql = f"SELECT {cols_str} FROM `{table_name}` ORDER BY `time`"

    print(f"  [LOAD] SELECT {len(select_cols)} 列 FROM {table_name} ...")
    t0 = time.time()

    df = pd.read_sql(sql, engine)

    # 确保数值列类型正确
    numeric_cols = ['price', 'change_pct', 'amount', 'high', 'low', 'open', 'pre_close']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    elapsed = time.time() - t0
    print(f"  [LOAD] 加载完成: {len(df)} 行, 耗时 {elapsed:.1f}s")

    return df


def load_table_data_streaming(engine, table_name: str, needed_columns: set,
                                batch_size: int = 50000):
    """
    【优化v5】时间分片读取，替代SSCursor
    每次独立查询一批时间点的数据，不依赖长连接，不会超时
    
    Args:
        engine: SQLAlchemy引擎
        table_name: 表名
        needed_columns: 需要的列集合
        batch_size: 每批目标行数（通过时间点数量控制）
    
    Yields:
        pd.DataFrame: 每批数据（按时间排序）
    """
    insp = inspect(engine)
    if not insp.has_table(table_name):
        return
    
    actual_cols = {col['name'] for col in insp.get_columns(table_name)}
    select_cols = sorted(needed_columns & actual_cols)
    
    if not select_cols:
        return
    
    for pk in [CODE_COL, 'time']:
        if pk in actual_cols and pk not in select_cols:
            select_cols.append(pk)
    
    cols_str = ", ".join([f"`{c}`" for c in select_cols])
    
    print(f"  [LOAD-CHUNK] 时间分片读取 {table_name} ...")
    t0 = time.time()
    total_rows = 0
    
    # 第1步：获取所有时间点（轻量查询）
    time_sql = f"SELECT DISTINCT `time` FROM `{table_name}` ORDER BY `time`"
    with engine.connect() as conn:
        result = conn.execute(text(time_sql))
        all_times = [row[0] for row in result.fetchall()]
    
    if not all_times:
        print(f"  [LOAD-CHUNK] 表为空")
        return
    
    # 每片包含的时间点数量
    # 实际数据：~400债券/tick，100个tick = ~40000行/片，接近FLUSH_SIZE
    chunk_time_count = 100
    
    print(f"  [LOAD-CHUNK] 共 {len(all_times)} 个时间点, 每批 {chunk_time_count} 个时间点")
    
    # 第2步：按时间分片读取
    for i in range(0, len(all_times), chunk_time_count):
        chunk_times = all_times[i:i + chunk_time_count]
        
        # 构建IN子句
        placeholders = ', '.join([f":t_{j}" for j in range(len(chunk_times))])
        chunk_sql = f"SELECT {cols_str} FROM `{table_name}` WHERE `time` IN ({placeholders}) ORDER BY `time`, `{CODE_COL}`"
        
        params = {f"t_{j}": t for j, t in enumerate(chunk_times)}
        
        df = pd.read_sql(text(chunk_sql), engine, params=params)
        
        if df.empty:
            continue
        
        total_rows += len(df)
        
        # 类型转换
        numeric_cols = ['price', 'change_pct', 'amount', 'high', 'low', 'open', 'pre_close']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
        yield df
    
    elapsed = time.time() - t0
    print(f"  [LOAD-CHUNK] 分片读取完成: {total_rows} 行, {len(all_times)} 个时间点, 耗时 {elapsed:.1f}s")


# ========== 扩展指标映射 ==========
# 扩展指标（存储在ext_indicators JSON中）映射到ext_indicators字段
EXT_INDICATOR_FIELDS = {
    'weighted_slope_2m', 'weighted_slope_5m', 'weighted_slope_15m',
    'change_1m_pct', 'price_acceleration',
    'mkt_weighted_slope_2m', 'mkt_weighted_slope_5m', 'mkt_weighted_slope_15m',
    'mkt_change_1m_pct', 'mkt_price_acceleration'
}

def map_fields_to_actual(fields_to_compute: list) -> list:
    """
    将用户指定的字段映射到实际的数据库字段
    扩展指标（如weighted_slope_2m）映射到ext_indicators
    """
    if not fields_to_compute:
        return None
    
    actual_fields = set()
    for f in fields_to_compute:
        if f in EXT_INDICATOR_FIELDS:
            actual_fields.add('ext_indicators')
        else:
            actual_fields.add(f)
    
    return list(actual_fields)


# ========== 字段确定 ==========
def determine_fields_to_compute(fields_to_compute, existing_columns, skip_existing, force):
    """
    确定实际需要计算的字段
    
    【参数优先级】force > skip_existing
    
    组合说明:
        组合1 (force=True): 
            效果: 强制重算所有字段，覆盖已有数据
            用途: 算法更新后、数据异常时
            注意: skip_existing参数被忽略
            
        组合2 (force=False + skip_existing=False):
            效果: 计算所有指定字段，可能覆盖已有数据
            用途: 首次回填、需要更新特定字段
            
        组合3 (force=False + skip_existing=True):
            效果: 只计算表中不存在的字段（增量回填）
            用途: 补充新字段、续跑中断任务（推荐日常使用）
    
    Args:
        fields_to_compute: 用户指定的字段列表，None=全部字段
        existing_columns: 表中已存在的列名集合
        skip_existing: 是否跳过已存在的列（force=False时生效）
        force: 是否强制重算（最高优先级）
        
    Returns:
        实际需要计算的字段列表
    """
    # 映射扩展指标到ext_indicators
    mapped_fields = map_fields_to_actual(fields_to_compute)
    all_fields = mapped_fields or get_field_names()
    
    # 组合1: force=True，强制重算所有字段（最高优先级）
    if force:
        if skip_existing:
            print(f"    [WARN] force=True 时，skip_existing={skip_existing} 被忽略")
            print(f"    [MODE] 强制重算模式: 将计算 {len(all_fields)} 个字段并覆盖已有数据")
        else:
            print(f"    [MODE] 强制重算模式: 将计算 {len(all_fields)} 个字段")
        return all_fields
    
    # 组合3: force=False + skip_existing=True，增量回填
    if skip_existing:
        missing_fields = [f for f in all_fields if f not in existing_columns]
        existing_fields = [f for f in all_fields if f in existing_columns]
        
        if existing_fields:
            print(f"    [MODE] 增量回填模式: 跳过 {len(existing_fields)} 个已有字段")
            print(f"    [SKIP] {existing_fields}")
        if missing_fields:
            print(f"    [MODE] 将计算 {len(missing_fields)} 个缺失字段")
            print(f"    [COMPUTE] {missing_fields}")
        else:
            print(f"    [MODE] 所有字段已存在，无需计算")
        return missing_fields
    
    # 组合2: force=False + skip_existing=False，全量计算
    print(f"    [MODE] 全量计算模式: 将计算 {len(all_fields)} 个字段")
    print(f"    [NOTE] 可能覆盖已有数据，但不会像force=True那样强制清空")
    return all_fields


# ========== 单日处理（独立函数，用于多进程） ==========
def process_single_day_standalone(date_str, fields_to_compute, skip_existing, force, db_url):
    """
    【优化v4】独立的单日处理函数
    流式读取（节省内存） + BatchWriter分批UPDATE JOIN（快速写入）
    """
    import traceback

    # 每个进程独立的引擎
    engine = create_db_engine(db_url, pool_size=3)

    try:
        table_name = f"{TABLE_PREFIX}{date_str}"

        # Schema检查
        schema_mgr = SchemaManager(engine)
        existing_columns = schema_mgr.get_existing_columns(table_name)
        if not existing_columns:
            return (date_str, True, f"表不存在", 0, 0)

        # 确定字段
        actual_fields = determine_fields_to_compute(
            fields_to_compute, existing_columns, skip_existing, force
        )
        if not actual_fields:
            return (date_str, True, f"无需计算", 0, 0)

        # 确保列存在
        field_defs_to_add = [get_field_def(f) for f in actual_fields if get_field_def(f)]
        schema_mgr.ensure_columns(table_name, field_defs_to_add)

        # 【修复】确保ext_indicators列是TEXT类型（旧表可能是VARCHAR）
        if 'ext_indicators' in actual_fields and 'ext_indicators' in existing_columns:
            try:
                insp = inspect(engine)
                cols = {c['name']: c for c in insp.get_columns(table_name)}
                if 'ext_indicators' in cols:
                    col_type = str(cols['ext_indicators']['type']).upper()
                    if 'TEXT' not in col_type and 'JSON' not in col_type:
                        print(f"  [FIX] ext_indicators列类型 {col_type} -> TEXT")
                        with engine.connect() as conn:
                            conn.execute(text(f"ALTER TABLE `{table_name}` MODIFY COLUMN `ext_indicators` TEXT NULL"))
                            conn.commit()
            except Exception as e:
                print(f"  [WARN] 修复ext_indicators列类型失败: {e}")

        # 确定源字段（只读取计算依赖列，节省内存）
        needed_columns = {CODE_COL, 'time'}
        for fname in actual_fields:
            fdef = get_field_def(fname)
            if fdef:
                needed_columns.update(fdef.depends)

        # 创建独立的计算引擎（状态隔离）
        compute_engine = ComputeEngine()
        fields_set = set(actual_fields)
        
        # 【优化v5】参数调优：5000行/批UPDATE JOIN，每5万行flush一次
        # 实际数据：~400债券×4800tick=192万行，每tick约400行
        # 5000行/批 × 10批 = 50000行/flush，耗时约20秒，远低于600秒超时
        writer = BatchWriter(engine, table_name, batch_size=5000)
        
        total_rows = 0
        all_results = []
        FLUSH_SIZE = 50000  # 每积累5万行结果执行一次写入（约10个批次）
        
        # 【新增】预估总行数，用于进度计算
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
            estimated_total = result.scalar() or 0
        
        # 【优化】流式读取数据（只读计算依赖列，节省内存）
        print(f"  [PROCESS] 开始流式处理 {table_name} ({estimated_total:,} 行) ...")
        t0 = time.time()
        total_rows_read = 0  # 已读取的行数（用于进度计算，一定到100%）
        
        for df_batch in load_table_data_streaming(engine, table_name, needed_columns, batch_size=50000):
            if df_batch.empty:
                continue
            
            total_rows_read += len(df_batch)
            
            # 逐tick计算
            grouped = df_batch.groupby('time', sort=True)
            
            for tick_time, df_tick in grouped:
                tick_time_str = str(tick_time)
                tick_results = compute_engine.process_tick(df_tick, tick_time_str, fields_set)
                
                codes_in_tick = df_tick[CODE_COL].tolist()
                for code in codes_in_tick:
                    row_result = {'bond_code': code, 'time': tick_time_str}
                    has_data = False
                    for field_name in actual_fields:
                        if field_name in tick_results:
                            val = tick_results[field_name]
                            if isinstance(val, dict):
                                row_result[field_name] = val.get(code)
                            else:
                                row_result[field_name] = val
                            has_data = True
                    if has_data:
                        all_results.append(row_result)
                        total_rows += 1
            
            # 达到FLUSH_SIZE时，执行批量写入
            if len(all_results) >= FLUSH_SIZE:
                writer.write_results(all_results, actual_fields)
                all_results = []
                
                # 【修复】进度基于已读取行数（保证到100%）
                elapsed = time.time() - t0
                progress = total_rows_read / estimated_total * 100 if estimated_total > 0 else 0
                speed = total_rows_read / elapsed if elapsed > 0 else 0
                remaining = (estimated_total - total_rows_read) / speed if speed > 0 else 0
                print(f"  [PROGRESS] 已处理 {total_rows_read:,}/{estimated_total:,} ({progress:.1f}%) | "
                      f"已写入 {writer.total_updated:,} | "
                      f"速度 {speed:.0f}行/秒 | 剩余 {remaining:.0f}s")
        
        # 写入剩余数据
        if all_results:
            writer.write_results(all_results, actual_fields)
        
        elapsed = time.time() - t0
        print(f"  [DONE] 处理完成: {total_rows} 行计算, {writer.total_updated} 行更新, 耗时 {elapsed:.1f}s")
        
        return (date_str, True, f"成功", total_rows, writer.total_updated)

    except Exception as e:
        return (date_str, False, traceback.format_exc(), 0, 0)
    finally:
        engine.dispose()


# ========== 单日处理（单进程模式，保持兼容） ==========
def process_single_day(engine, date_str, fields_to_compute, skip_existing, force):
    """单日处理（单进程模式，用于兼容）"""
    result = process_single_day_standalone(
        date_str,
        fields_to_compute,
        skip_existing,
        force,
        DB_URL
    )
    date_str, success, message, rows, updated = result

    if success:
        print(f"  [DONE] {date_str}: {message}, {rows}行计算, {updated}行更新")
    else:
        print(f"  [ERROR] {date_str}:\n{message}")
        raise Exception(message)


# ========== 参数解析 ==========
def parse_args():
    parser = argparse.ArgumentParser(
        description='统一字段回填引擎 v2.2 - 支持多进程并行 + 交易日期过滤',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
参数组合说明:
  组合1 (默认): --force
    效果: 强制重算所有字段，覆盖已有数据
    用途: 算法更新后、确保数据一致性
    
  组合2: 不指定--force
    ├─ 默认(--skip-existing=False): 计算所有字段，可能覆盖
    └─ --skip-existing: 只计算缺失字段（增量回填，推荐日常使用）

示例:
  # 全量重算并覆盖（默认）
  python scripts/backfill_unified.py --start 20260701 --end 20260731
  
  # 增量回填（只补充缺失字段）
  python scripts/backfill_unified.py --start 20260701 --end 20260731 --skip-existing
  
  # 指定字段
  python scripts/backfill_unified.py --date 20260709 --fields min1_amount_rank slope_short
  
  # 并行8进程
  python scripts/backfill_unified.py --start 20260701 --end 20260731 --workers 8
        """
    )

    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument('--date', type=str, help='单日回填，格式: YYYYMMDD')
    date_group.add_argument('--start', type=str, help='范围回填起始日期，格式: YYYYMMDD')

    parser.add_argument('--end', type=str, help='范围回填结束日期，格式: YYYYMMDD')
    parser.add_argument('--fields', nargs='+', type=str, default=None, help='指定回填字段，默认全部')
    parser.add_argument('--skip-existing', action='store_true', default=False, 
                        help='跳过已有字段（force=False时生效），默认False')
    parser.add_argument('--force', action='store_true', default=True,
                        help='强制重算并覆盖（最高优先级），默认True')
    parser.add_argument('--workers', type=int, default=None, 
                        help='并行进程数，默认自动计算: min(CPU-1, 8, 日期数)')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')

    args = parser.parse_args()

    if args.start and not args.end:
        parser.error("--start 需要配合 --end 使用")

    return args


def generate_date_range(start: str, end: str) -> list:
    """生成日期范围列表（所有日期，包含非交易日）"""
    start_dt = datetime.strptime(start, '%Y%m%d')
    end_dt = datetime.strptime(end, '%Y%m%d')

    dates = []
    current = start_dt
    while current <= end_dt:
        dates.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)

    return dates


def get_trading_dates(engine, date_start: str, date_end: str) -> list:
    """
    从 data_jyrl 获取区间内的交易日期（自动过滤非交易日）
    
    Args:
        engine: 数据库引擎
        date_start: 开始日期 '20260701'
        date_end: 结束日期 '20260731'
        
    Returns:
        交易日期列表 ['20260701', '20260703', ...]（仅包含实际交易日）
    """
    # 转换为带横线格式
    db_start = f"{date_start[:4]}-{date_start[4:6]}-{date_start[6:]}"
    db_end = f"{date_end[:4]}-{date_end[4:6]}-{date_end[6:]}"
    
    sql = text("""
        SELECT DISTINCT trade_date as date 
        FROM data_jyrl 
        WHERE trade_date >= :date_start AND trade_date <= :date_end
          AND trade_status = 1
        ORDER BY trade_date
    """)
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={
                'date_start': db_start,
                'date_end': db_end
            })
        
        if not df.empty:
            # 转换回无横线格式
            dates = [str(d).replace('-', '') for d in df['date'].tolist()]
        else:
            dates = []
        
        return dates
    except Exception as e:
        print(f"  [WARN] 获取交易日期失败: {e}，将使用所有日期")
        # 失败时回退到所有日期
        return generate_date_range(date_start, date_end)


# ========== 主函数 ==========
def main(config=None):
    """
    主入口函数
    
    Args:
        config: 可选配置字典，为None时根据 USE_DEFAULT_CONFIG 决定使用代码配置或命令行参数
    
    使用方式:
        # 1. 命令行模式（默认）
        python backfill_unified.py --start 20260701 --end 20260731
        
        # 2. 代码配置模式（设置 USE_DEFAULT_CONFIG = True）
        python backfill_unified.py
        
        # 3. 作为模块导入
        from backfill_unified import main
        main(config={'mode': 'range', 'start': '20260701', 'end': '20260731'})
    """
    # 确定配置来源
    if config is not None:
        # 显式传入配置
        cfg = config
        use_code_config = True
    elif USE_DEFAULT_CONFIG:
        # 使用代码中的默认配置
        cfg = DEFAULT_CONFIG
        use_code_config = True
    else:
        # 使用命令行参数
        use_code_config = False
    
    # 构建 args 对象
    if use_code_config:
        class Args:
            pass
        args = Args()
        
        if cfg.get('mode') == 'single':
            args.date = cfg.get('date')
            args.start = None
            args.end = None
        else:
            args.date = None
            args.start = cfg.get('start')
            args.end = cfg.get('end')
            
        args.fields = cfg.get('fields')
        args.skip_existing = cfg.get('skip_existing', False)
        args.force = cfg.get('force', False)
        args.workers = cfg.get('workers')
        args.dry_run = cfg.get('dry_run', False)
    else:
        # 命令行模式
        args = parse_args()

    # 确定日期列表（自动过滤为交易日）
    if args.date:
        dates = [args.date]
        use_parallel = False
    else:
        # 先获取交易日期（从 data_jyrl 查询）
        engine_temp = create_db_engine(pool_size=1)
        try:
            dates = get_trading_dates(engine_temp, args.start, args.end)
            print(f"  [TRADING] 从 {args.start}~{args.end} 过滤出 {len(dates)} 个交易日")
        except Exception as e:
            print(f"  [WARN] 获取交易日期失败: {e}")
            dates = generate_date_range(args.start, args.end)
        finally:
            engine_temp.dispose()
        
        use_parallel = len(dates) > 1

    print("=" * 60)
    print("  统一字段回填引擎 v2.2 (优化版)")
    print("=" * 60)
    print(f"  配置模式: {'代码配置' if use_code_config else '命令行参数'}")
    print(f"  日期范围: {dates[0] if dates else 'N/A'} ~ {dates[-1] if dates else 'N/A'} ({len(dates)}天)")
    print(f"  指定字段: {args.fields or '全部'}")
    print(f"  跳过已有: {args.skip_existing} (True=只补充缺失字段)")
    print(f"  强制重算: {args.force} (True=覆盖已有数据)")
    print(f"  并行模式: {'是' if use_parallel else '否'}")

    if args.dry_run:
        print("\n  [DRY-RUN] 仅显示计划，不执行写入")
        print(f"\n  可用字段 ({len(FIELD_REGISTRY)}):")
        for fdef in FIELD_REGISTRY:
            print(f"    {fdef.name:25s} [{fdef.category:10s}] {fdef.db_type:6s} | {fdef.description}")
        return

    total_start = time.time()

    if use_parallel:
        # 多进程并行模式
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor, as_completed

        cpu_count = mp.cpu_count()
        # 并行进程数计算逻辑：
        # 1. 保留1核给系统（cpu_count - 1）
        # 2. 最多8进程（避免数据库连接过多）
        # 3. 不超过日期数（避免空转）
        # 4. 用户可手动指定覆盖 (--workers)
        max_workers = args.workers or min(cpu_count - 1, 8, len(dates))
        max_workers = max(1, max_workers)

        print(f"  CPU核数: {cpu_count}")
        print(f"  并行进程: {max_workers} (计算: min(CPU-1={cpu_count-1}, 8, 日期数={len(dates)}))")
        print(f"  每进程独立计算引擎（状态隔离）")
        print("=" * 60)

        # 准备任务
        tasks = [(d, args.fields, args.skip_existing, args.force, DB_URL) for d in dates]

        completed = 0
        failed = 0
        total_rows = 0
        total_updated = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_date = {
                executor.submit(process_single_day_standalone, *task): task[0]
                for task in tasks
            }

            for future in as_completed(future_to_date):
                date_str, success, message, rows, updated = future.result()
                completed += 1

                if success:
                    total_rows += rows
                    total_updated += updated
                    print(f"[{completed}/{len(dates)}] ✓ {date_str}: {message} ({rows}行/{updated}更新)")
                else:
                    failed += 1
                    print(f"[{completed}/{len(dates)}] ✗ {date_str} FAILED:")
                    print(message[:500] + "..." if len(message) > 500 else message)

        print(f"\n{'='*60}")
        print(f"  回填完成: 成功 {len(dates)-failed} 天, 失败 {failed} 天")
        print(f"  总计: {total_rows} 行计算, {total_updated} 行更新")

    else:
        # 单进程模式（单日或显式单进程）
        print("=" * 60)
        engine = create_db_engine(pool_size=5)

        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("  [DB] 连接成功 ✓")
        except Exception as e:
            print(f"  [DB] 连接失败: {e}")
            sys.exit(1)

        for date_str in dates:
            try:
                process_single_day(engine, date_str, args.fields,
                                   args.skip_existing, args.force)
            except Exception as e:
                print(f"  [ERROR] 处理 {date_str} 失败: {e}")
                import traceback
                traceback.print_exc()
                continue

        engine.dispose()

    total_elapsed = time.time() - total_start
    print(f"  总耗时: {total_elapsed:.1f}s")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
