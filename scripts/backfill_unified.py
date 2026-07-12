"""
统一字段回填引擎 - 主入口脚本 (优化版 v2.0)
支持多进程并行 + 批量UPDATE

用法:
    # 回填单日全部缺失字段
    python scripts/backfill_unified.py --date 20260710

    # 回填日期范围（自动并行）
    python scripts/backfill_unified.py --start 20260706 --end 20260710

    # 只回填指定字段
    python scripts/backfill_unified.py --date 20260709 --fields min1_amount_rank

    # 只补缺失字段（已有数据的跳过）
    python scripts/backfill_unified.py --date 20260706 --skip-existing

    # 强制全量重算（覆盖已有数据）
    python scripts/backfill_unified.py --date 20260710 --force

    # 指定并行进程数（默认CPU核数-1）
    python scripts/backfill_unified.py --start 20260701 --end 20260731 --workers 8
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


def create_db_engine(db_url=None, pool_size=5):
    """创建优化的数据库引擎"""
    url = db_url or DB_URL
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=pool_size * 2,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
        connect_args={
            'connect_timeout': 10,
            'read_timeout': 300,
            'write_timeout': 300,
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

    def __init__(self, engine, table_name, batch_size=5000):
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
        """使用临时表+UPDATE JOIN实现批量更新"""
        from sqlalchemy import text

        temp_table = f"{self.table_name}_temp_{int(time.time() * 1000)}"

        try:
            with self.engine.connect() as conn:
                # 1. 创建临时表
                field_defs = ', '.join([f'{f} FLOAT' for f in fields])
                create_sql = f"""
                    CREATE TEMPORARY TABLE `{temp_table}` (
                        bond_code VARCHAR(20),
                        time VARCHAR(20),
                        {field_defs},
                        PRIMARY KEY (bond_code, time)
                    ) ENGINE=MEMORY
                """
                conn.execute(text(create_sql))
                conn.commit()

                # 2. 分批插入临时表
                columns = ['bond_code', 'time'] + fields
                data = []
                for _, row in df.iterrows():
                    row_data = []
                    for col in columns:
                        val = row.get(col)
                        if pd.isna(val):
                            row_data.append(None)
                        else:
                            row_data.append(float(val) if isinstance(val, (int, float, np.number)) else val)
                    data.append(row_data)

                # 每批10000行插入
                insert_batch_size = 10000
                for i in range(0, len(data), insert_batch_size):
                    batch = data[i:i+insert_batch_size]
                    placeholders = ', '.join(['(' + ', '.join(['%s'] * len(columns)) + ')'] * len(batch))
                    flat_values = [item for sublist in batch for item in sublist]

                    insert_sql = f"INSERT INTO `{temp_table}` ({', '.join(columns)}) VALUES {placeholders}"
                    # 修正：使用executemany方式
                    conn.execute(text(f"INSERT INTO `{temp_table}` ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"), batch)
                    conn.commit()

                # 3. UPDATE JOIN
                set_clauses = ', '.join([f't.{f} = s.{f}' for f in fields])
                update_sql = f"""
                    UPDATE `{self.table_name}` t
                    INNER JOIN `{temp_table}` s ON t.bond_code = s.bond_code AND t.time = s.time
                    SET {set_clauses}
                """
                result = conn.execute(text(update_sql))
                conn.commit()

                self.total_updated = result.rowcount
                self.total_batches = 1

                print(f"    [BULK] 临时表写入 {len(df)} 行, UPDATE JOIN 更新 {self.total_updated} 行")

        finally:
            # 清理临时表
            try:
                with self.engine.connect() as conn:
                    conn.execute(text(f"DROP TEMPORARY TABLE IF EXISTS `{temp_table}`"))
                    conn.commit()
            except:
                pass


# ========== 数据加载 ==========
def load_table_data(engine, table_name: str, needed_columns: set) -> pd.DataFrame:
    """加载表数据（全表读入，按时间排序）"""
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


# ========== 字段确定 ==========
def determine_fields_to_compute(fields_to_compute, existing_columns, skip_existing, force):
    """确定实际需要计算的字段"""
    if force:
        return fields_to_compute or get_field_names()

    all_fields = fields_to_compute or get_field_names()

    if skip_existing:
        return [f for f in all_fields if f not in existing_columns]

    return all_fields


# ========== 单日处理（独立函数，用于多进程） ==========
def process_single_day_standalone(date_str, fields_to_compute, skip_existing, force, db_url):
    """
    独立的单日处理函数（用于多进程）
    每个进程创建自己的引擎和计算引擎，状态完全隔离
    """
    import traceback

    # 每个进程独立的引擎（连接池大小=2）
    engine = create_db_engine(db_url, pool_size=2)

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

        # 确定源字段
        needed_columns = {CODE_COL, 'time'}
        for fname in actual_fields:
            fdef = get_field_def(fname)
            if fdef:
                needed_columns.update(fdef.depends)

        # 加载数据
        df = load_table_data(engine, table_name, needed_columns)
        if df.empty:
            return (date_str, True, f"表为空", 0, 0)

        # 创建独立的计算引擎（状态隔离）
        compute_engine = ComputeEngine()

        # 逐tick计算（业务逻辑完全复用）
        grouped = df.groupby('time', sort=True)
        tick_count = len(grouped)

        all_results = []
        fields_set = set(actual_fields)

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

        # 批量写入
        if all_results:
            writer = BatchWriter(engine, table_name, 5000)
            writer.write_results(all_results, actual_fields)
            return (date_str, True, f"成功", len(all_results), writer.total_updated)
        else:
            return (date_str, True, f"无结果", 0, 0)

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
        description='统一字段回填引擎 v2.0 - 支持多进程并行',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/backfill_unified.py --date 20260710
  python scripts/backfill_unified.py --start 20260706 --end 20260710
  python scripts/backfill_unified.py --date 20260709 --fields min1_amount_rank
  python scripts/backfill_unified.py --date 20260706 --skip-existing
  python scripts/backfill_unified.py --date 20260710 --force
  python scripts/backfill_unified.py --start 20260701 --end 20260731 --workers 8
        """
    )

    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument('--date', type=str, help='单日回填，格式: YYYYMMDD')
    date_group.add_argument('--start', type=str, help='范围回填起始日期，格式: YYYYMMDD')

    parser.add_argument('--end', type=str, help='范围回填结束日期，格式: YYYYMMDD')
    parser.add_argument('--fields', nargs='+', type=str, default=None, help='指定回填字段')
    parser.add_argument('--skip-existing', action='store_true', help='跳过已有列')
    parser.add_argument('--force', action='store_true', help='强制重算')
    parser.add_argument('--workers', type=int, default=None, help='并行进程数（默认CPU-1）')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')

    args = parser.parse_args()

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


# ========== 主函数 ==========
def main():
    args = parse_args()

    # 确定日期列表
    if args.date:
        dates = [args.date]
        use_parallel = False
    else:
        dates = generate_date_range(args.start, args.end)
        use_parallel = len(dates) > 1

    print("=" * 60)
    print("  统一字段回填引擎 v2.0 (优化版)")
    print("=" * 60)
    print(f"  日期范围: {dates[0]} ~ {dates[-1]} ({len(dates)}天)")
    print(f"  指定字段: {args.fields or '全部'}")
    print(f"  跳过已有: {args.skip_existing}")
    print(f"  强制重算: {args.force}")
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
        max_workers = args.workers or min(cpu_count - 1, 8, len(dates))
        max_workers = max(1, max_workers)

        print(f"  CPU核数: {cpu_count}")
        print(f"  并行进程: {max_workers}")
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
        engine = create_db_engine(pool_size=2)

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
