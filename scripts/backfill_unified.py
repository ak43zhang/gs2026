"""
统一字段回填引擎 - 主入口脚本

用法:
    # 回填单日全部缺失字段
    python scripts/backfill_unified.py --date 20260710

    # 回填日期范围
    python scripts/backfill_unified.py --start 20260706 --end 20260710

    # 只回填指定字段
    python scripts/backfill_unified.py --date 20260709 --fields min1_amount_rank

    # 只补缺失字段（已有数据的跳过）
    python scripts/backfill_unified.py --date 20260706 --skip-existing

    # 强制全量重算（覆盖已有数据）
    python scripts/backfill_unified.py --date 20260710 --force
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


# ========== 配置 ==========
DB_URL = "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8"
TABLE_PREFIX = "monitor_zq_sssj_"
BATCH_SIZE = 1000  # 每批UPDATE行数
CODE_COL = 'bond_code'  # 主键列名


def create_db_engine():
    """创建数据库引擎"""
    return create_engine(DB_URL, pool_size=5, max_overflow=10, pool_recycle=3600)


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
                        # 列可能已存在（并发情况）
                        if 'Duplicate column' in str(e):
                            pass
                        else:
                            print(f"  [ERROR] 添加列 {field_def.name} 失败: {e}")
                            conn.rollback()
        return added

    @staticmethod
    def _map_db_type(field_type: str) -> str:
        """映射字段类型到MySQL列定义"""
        type_map = {
            'INT': 'INT',
            'FLOAT': 'FLOAT',
            'DOUBLE': 'DOUBLE',
            'JSON': 'JSON',
            'TEXT': 'TEXT',
        }
        return type_map.get(field_type.upper(), 'FLOAT')


# ========== 批量写入器 ==========
class BatchWriter:
    """高效批量UPDATE回写器"""

    def __init__(self, engine, table_name: str, batch_size: int = BATCH_SIZE):
        self.engine = engine
        self.table_name = table_name
        self.batch_size = batch_size
        self.total_updated = 0
        self.total_batches = 0

    def write_results(self, results_by_row: list, fields: list):
        """
        批量UPDATE回写

        Args:
            results_by_row: [{'bond_code': ..., 'time': ..., 'field1': val1, ...}, ...]
            fields: 需要更新的字段名列表
        """
        if not results_by_row:
            return

        # 构建UPDATE SQL
        set_clause = ", ".join([f"`{f}` = :{f}" for f in fields])
        sql = text(f"""
            UPDATE `{self.table_name}`
            SET {set_clause}
            WHERE `bond_code` = :bond_code AND `time` = :time
        """)

        # 分批提交
        with self.engine.connect() as conn:
            batch = []
            for row in results_by_row:
                batch.append(row)
                if len(batch) >= self.batch_size:
                    conn.execute(sql, batch)
                    conn.commit()
                    self.total_updated += len(batch)
                    self.total_batches += 1
                    batch = []

            # 剩余的
            if batch:
                conn.execute(sql, batch)
                conn.commit()
                self.total_updated += len(batch)
                self.total_batches += 1


# ========== 主流程 ==========
def determine_fields_to_compute(requested_fields: list, existing_columns: set,
                                skip_existing: bool, force: bool) -> list:
    """
    确定需要计算的字段列表

    Args:
        requested_fields: 用户指定的字段（None表示全部）
        existing_columns: 表中已存在的列
        skip_existing: 是否跳过已有列
        force: 是否强制重算
    """
    all_field_names = get_field_names()

    if requested_fields:
        # 用户指定了字段
        target_fields = [f for f in requested_fields if f in all_field_names]
        if not target_fields:
            print(f"  [ERROR] 指定的字段都不在注册表中: {requested_fields}")
            print(f"  可用字段: {all_field_names}")
            return []
    else:
        # 全部字段
        target_fields = all_field_names

    if force:
        # 强制模式：不管是否存在都重算
        return target_fields

    if skip_existing:
        # 跳过已存在列（有列定义就跳过）
        target_fields = [f for f in target_fields if f not in existing_columns]

    return target_fields


def load_table_data(engine, table_name: str, needed_columns: set) -> pd.DataFrame:
    """
    加载表数据（全表读入，按时间排序）

    Args:
        engine: SQLAlchemy引擎
        table_name: 表名
        needed_columns: 需要读取的列集合（源字段 + 主键）
    """
    # 先确认表存在哪些列
    insp = inspect(engine)
    if not insp.has_table(table_name):
        return pd.DataFrame()

    actual_cols = {col['name'] for col in insp.get_columns(table_name)}

    # 只SELECT实际存在的列
    select_cols = sorted(needed_columns & actual_cols)
    if not select_cols:
        return pd.DataFrame()

    # 确保主键列在内
    for pk in [CODE_COL, 'time']:
        if pk in actual_cols and pk not in select_cols:
            select_cols.append(pk)

    cols_str = ", ".join([f"`{c}`" for c in select_cols])
    sql = f"SELECT {cols_str} FROM `{table_name}` ORDER BY `time`"

    print(f"  [LOAD] SELECT {len(select_cols)} 列 FROM {table_name} ORDER BY time ...")
    t0 = time.time()

    df = pd.read_sql(sql, engine)

    elapsed = time.time() - t0
    print(f"  [LOAD] 加载完成: {len(df)} 行, 耗时 {elapsed:.1f}s")

    return df


def process_single_day(engine, date_str: str, fields_to_compute: list,
                       skip_existing: bool, force: bool):
    """
    处理单日数据的完整流程

    Args:
        engine: SQLAlchemy引擎
        date_str: 日期字符串 YYYYMMDD
        fields_to_compute: 需要计算的字段列表
        skip_existing: 是否跳过已有数据
        force: 是否强制重算
    """
    table_name = f"{TABLE_PREFIX}{date_str}"
    print(f"\n{'='*60}")
    print(f"  处理日期: {date_str} | 表: {table_name}")
    print(f"{'='*60}")

    # 1. Schema检查
    schema_mgr = SchemaManager(engine)
    existing_columns = schema_mgr.get_existing_columns(table_name)
    if not existing_columns:
        print(f"  [SKIP] 表 {table_name} 不存在")
        return

    # 确定实际要计算的字段
    actual_fields = determine_fields_to_compute(
        fields_to_compute, existing_columns, skip_existing, force
    )
    if not actual_fields:
        print(f"  [SKIP] 无需计算的字段")
        return

    print(f"  [PLAN] 将计算 {len(actual_fields)} 个字段: {actual_fields}")

    # 2. 确保列存在（ALTER TABLE ADD COLUMN）
    field_defs_to_add = [get_field_def(f) for f in actual_fields if get_field_def(f)]
    schema_mgr.ensure_columns(table_name, field_defs_to_add)

    # 3. 确定需要读取的源字段
    needed_columns = {CODE_COL, 'time'}
    for fname in actual_fields:
        fdef = get_field_def(fname)
        if fdef:
            needed_columns.update(fdef.depends)

    # 加载数据
    df = load_table_data(engine, table_name, needed_columns)
    if df.empty:
        print(f"  [SKIP] 表为空")
        return

    # 确保数值列类型正确
    numeric_cols = ['price', 'change_pct', 'amount', 'high', 'low', 'open', 'pre_close']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # 4. 按时间分组，逐tick处理
    print(f"  [COMPUTE] 开始逐tick计算 ...")
    t0 = time.time()

    compute_engine = ComputeEngine()
    fields_set = set(actual_fields)

    # 按time分组（保持时间正序）
    grouped = df.groupby('time', sort=True)
    tick_count = len(grouped)
    print(f"  [COMPUTE] 共 {tick_count} 个tick, {len(df)} 行数据")

    # 收集所有结果 [{bond_code, time, field1, field2, ...}, ...]
    all_results = []
    progress_interval = max(1, tick_count // 20)  # 每5%打印一次

    for idx, (tick_time, df_tick) in enumerate(grouped):
        # 确保tick_time是字符串
        tick_time_str = str(tick_time)

        # 计算
        tick_results = compute_engine.process_tick(df_tick, tick_time_str, fields_set)

        # 收集结果到行格式
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

        # 进度
        if (idx + 1) % progress_interval == 0:
            pct = (idx + 1) / tick_count * 100
            print(f"    进度: {pct:.0f}% ({idx+1}/{tick_count} ticks)")

    elapsed = time.time() - t0
    print(f"  [COMPUTE] 计算完成: {len(all_results)} 行结果, 耗时 {elapsed:.1f}s")

    # 5. 批量UPDATE回写
    if not all_results:
        print(f"  [SKIP] 无结果需要写入")
        return

    print(f"  [WRITE] 开始批量UPDATE ({BATCH_SIZE}行/批) ...")
    t0 = time.time()

    writer = BatchWriter(engine, table_name, BATCH_SIZE)
    writer.write_results(all_results, actual_fields)

    elapsed = time.time() - t0
    print(f"  [WRITE] 写入完成: {writer.total_updated} 行, "
          f"{writer.total_batches} 批, 耗时 {elapsed:.1f}s")

    print(f"  [DONE] {date_str} 处理完毕 ✓")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='统一字段回填引擎 - 回填历史数据表的缺失字段',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/backfill_unified.py --date 20260710
  python scripts/backfill_unified.py --start 20260706 --end 20260710
  python scripts/backfill_unified.py --date 20260709 --fields min1_amount_rank slope_short
  python scripts/backfill_unified.py --date 20260706 --skip-existing
  python scripts/backfill_unified.py --date 20260710 --force
        """
    )

    # 日期参数（互斥组）
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument('--date', type=str,
                            help='单日回填，格式: YYYYMMDD')
    date_group.add_argument('--start', type=str,
                            help='范围回填起始日期，格式: YYYYMMDD（需配合--end）')

    parser.add_argument('--end', type=str,
                        help='范围回填结束日期，格式: YYYYMMDD')

    # 字段选择
    parser.add_argument('--fields', nargs='+', type=str, default=None,
                        help='指定回填的字段名（空格分隔），默认全部')

    # 模式选项
    parser.add_argument('--skip-existing', action='store_true',
                        help='跳过表中已存在的列（不覆盖）')
    parser.add_argument('--force', action='store_true',
                        help='强制重算所有字段（覆盖已有数据）')

    # 其他
    parser.add_argument('--dry-run', action='store_true',
                        help='只检查不执行（显示将要做什么）')

    args = parser.parse_args()

    # 验证日期范围
    if args.start and not args.end:
        parser.error("--start 需要配合 --end 使用")

    return args


def generate_date_range(start: str, end: str) -> list:
    """生成日期范围列表"""
    start_dt = datetime.strptime(start, '%Y%m%d')
    end_dt = datetime.strptime(end, '%Y%m%d')

    dates = []
    current = start_dt
    while current <= end_dt:
        dates.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)

    return dates


def main():
    args = parse_args()

    # 确定日期列表
    if args.date:
        dates = [args.date]
    else:
        dates = generate_date_range(args.start, args.end)

    print("=" * 60)
    print("  统一字段回填引擎 v1.0")
    print("=" * 60)
    print(f"  日期范围: {dates[0]} ~ {dates[-1]} ({len(dates)}天)")
    print(f"  指定字段: {args.fields or '全部'}")
    print(f"  跳过已有: {args.skip_existing}")
    print(f"  强制重算: {args.force}")
    print(f"  试运行:   {args.dry_run}")

    if args.dry_run:
        print("\n  [DRY-RUN] 仅显示计划，不执行写入")
        # 显示所有可用字段
        print(f"\n  可用字段 ({len(FIELD_REGISTRY)}):")
        for fdef in FIELD_REGISTRY:
            print(f"    {fdef.name:20s} [{fdef.category:8s}] {fdef.db_type:5s} | {fdef.description}")
        return

    # 创建引擎
    print(f"\n  [DB] 连接数据库 ...")
    engine = create_db_engine()

    # 测试连接
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"  [DB] 连接成功 ✓")
    except Exception as e:
        print(f"  [DB] 连接失败: {e}")
        sys.exit(1)

    # 逐日处理
    total_start = time.time()
    for date_str in dates:
        try:
            process_single_day(engine, date_str, args.fields,
                               args.skip_existing, args.force)
        except Exception as e:
            print(f"  [ERROR] 处理 {date_str} 失败: {e}")
            import traceback
            traceback.print_exc()
            continue

    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"  全部完成! 共处理 {len(dates)} 天, 总耗时 {total_elapsed:.1f}s")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
