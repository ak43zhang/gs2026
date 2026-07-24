#!/usr/bin/env python3
"""
JSON扩展字段快速回填脚本（字段级独立更新版）

核心特点：
- 计算逻辑复用 compute_engine.py（与实时计算一致）
- 只修改指定key，不影响JSON中的其他字段
- 默认覆盖指定key的value
- 可选--skip-existing跳过已有key的行
- 可选--backup启用备份模式（回填前自动备份表）

配置修改（在代码中修改 CONFIG 字典）：
    CONFIG = {
        'DEFAULT_FIELDS': ['mkt_shape', 'mkt_shape_detail'],  # 默认回填字段
        'DEFAULT_START': '20260723',                          # 默认开始日期
        'DEFAULT_END': '20260723',                            # 默认结束日期
        'DEFAULT_WORKERS': 8,                                 # 默认并行数
        'DEFAULT_BACKUP': True,                               # 默认启用备份
        'DEFAULT_SKIP_EXISTING': False,                       # 默认不跳过已有
    }

用法：
    # 直接运行（使用 CONFIG 中的默认配置）
    python backfill_json_fields.py
    
    # 命令行参数（覆盖默认配置）
    python backfill_json_fields.py --start 20260701 --end 20260731 --fields mkt_shape
    
    # 跳过已有（只填充缺失key的行）
    python backfill_json_fields.py --skip-existing
    
    # 不备份直接回填
    python backfill_json_fields.py --no-backup
"""

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set, Tuple, Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text

# ==================== CONFIG（所有配置在此修改）====================
# 回填配置 - 所有参数集中在此修改
CONFIG = {
    # 数据库配置
    'DB_URL': "mysql+pymysql://root:123456@192.168.0.101:3306/gs?charset=utf8",
    'TABLE_PREFIX': "monitor_zq_sssj_",
    
    # 默认回填字段
    'DEFAULT_FIELDS': ['mkt_shape', 'mkt_shape_detail'],
    
    # 默认日期范围
    'DEFAULT_START': '20260723',
    'DEFAULT_END': '20260723',
    
    # 默认并行数
    'DEFAULT_WORKERS': 1,
    
    # 默认每批时间点数量（时间分片读取）
    'DEFAULT_CHUNK_TIME_COUNT': 100,
    
    # 默认是否启用备份模式（True=备份，False=不备份）
    'DEFAULT_BACKUP': True,
    
    # 默认是否跳过已有（True=跳过已有key的行，False=覆盖）
    'DEFAULT_SKIP_EXISTING': False,
}

# 兼容别名（代码中使用）
DB_URL = CONFIG['DB_URL']
TABLE_PREFIX = CONFIG['TABLE_PREFIX']
DEFAULT_FIELDS = CONFIG['DEFAULT_FIELDS']
DEFAULT_START = CONFIG['DEFAULT_START']
DEFAULT_END = CONFIG['DEFAULT_END']
DEFAULT_WORKERS = CONFIG['DEFAULT_WORKERS']
# =========================================================

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


def load_table_data_streaming(engine, table_name: str, needed_columns: set, chunk_time_count: int = 200):
    """
    【优化】时间分片流式读取
    
    替代原来的单债券查询，按时间批次读取数据。
    原方案：400只债券 = 400次查询
    新方案：4800tick / 200tick每片 = 24次查询
    
    Args:
        engine: SQLAlchemy引擎
        table_name: 表名
        needed_columns: 需要的列集合
        chunk_time_count: 每批时间点数量（默认200）
    
    Yields:
        pd.DataFrame: 每批数据（按时间排序）
    """
    # 1. 获取所有时间点（轻量查询）
    time_sql = f"SELECT DISTINCT `time` FROM `{table_name}` ORDER BY `time`"
    with engine.connect() as conn:
        result = conn.execute(text(time_sql))
        all_times = [row[0] for row in result.fetchall()]
    
    if not all_times:
        return
    
    print(f"  [LOAD] 共 {len(all_times)} 个时间点, 每批 {chunk_time_count} 个")
    
    # 2. 按时间片批量查询
    for i in range(0, len(all_times), chunk_time_count):
        chunk_times = all_times[i:i + chunk_time_count]
        
        # 构建IN子句（使用参数化查询）
        placeholders = ', '.join([f"'{t}'" for t in chunk_times])
        cols_str = ", ".join([f"`{c}`" for c in sorted(needed_columns)])
        
        chunk_sql = f"""
            SELECT {cols_str} 
            FROM `{table_name}` 
            WHERE `time` IN ({placeholders}) 
            ORDER BY `time`, `bond_code`
        """
        
        df = pd.read_sql(text(chunk_sql), engine)
        
        if not df.empty:
            yield df


def _bulk_update_json_fields(engine, table_name: str, df_updates: pd.DataFrame,
                             target_fields: List[str]) -> int:
    """
    【优化】批量UPDATE JSON字段（临时表+分批UPDATE）
    
    优化点（借鉴backfill_unified.py）：
    1. 数据透视：行存储→列存储
    2. 分批UPDATE：1000行/批，避免超时和单点失败
    3. 错误隔离：单批失败不影响其他批
    
    Args:
        engine: SQLAlchemy引擎
        table_name: 目标表名
        df_updates: DataFrame [bond_code, time, field_name, field_value]
        target_fields: 目标字段列表
    
    Returns:
        int: 更新的行数
    """
    if df_updates.empty:
        return 0
    
    import time
    
    # 1. 数据预处理
    # 【修复】去重必须按 (bond_code, time, field_name) 三键，
    # 否则会误删同一 (bond_code, time) 下的不同字段记录！
    df = df_updates.drop_duplicates(subset=['bond_code', 'time', 'field_name'], keep='last')
    
    # 透视：行存储→列存储
    # 原：bond_code | time | field_name | field_value
    # 新：bond_code | time | mkt_shape | mkt_shape_detail
    df_pivot = df.pivot(index=['bond_code', 'time'],
                        columns='field_name',
                        values='field_value').reset_index()
    
    # 确保所有目标字段都存在
    for field in target_fields:
        if field not in df_pivot.columns:
            df_pivot[field] = None
    
    # 2. 【优化】直接逐行UPDATE + 分批提交（无需临时表）
    # 说明：
    #   - 逐行UPDATE使用行级锁，锁竞争小
    #   - 每批提交一次，避免大事务和长时间锁持有
    #   - 批次间sleep，给IO和锁释放缓冲
    #   - 独立连接每批，配合autocommit=OFF环境
    BATCH_SIZE = 500       # 每批行数
    SLEEP_SECONDS = 0.02   # 批次间sleep
    total_updated = 0
    total_failed = 0
    total_rows = len(df_pivot)
    total_batches = (total_rows - 1) // BATCH_SIZE + 1
    
    print(f"    [UPDATE] 逐行更新，共 {total_rows} 行，每批 {BATCH_SIZE} 条，{total_batches} 批...")
    t0 = time.time()
    
    for batch_start in range(0, total_rows, BATCH_SIZE):
        batch_num = batch_start // BATCH_SIZE + 1
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df_pivot.iloc[batch_start:batch_end]
        
        if batch_df.empty:
            continue
        
        # 每批使用独立连接（配合autocommit=OFF，确保及时释放）
        batch_updated = 0
        with engine.connect() as conn:
            for _, row in batch_df.iterrows():
                # 构建JSON_SET参数
                json_set_args = ["COALESCE(ext_indicators, '{}')"]
                for field in target_fields:
                    value = row[field]
                    if value is not None and pd.notna(value):
                        json_set_args.append(f"'$.{field}'")
                        # 处理字符串引号转义
                        if isinstance(value, str):
                            value = value.replace("'", "''")
                            json_set_args.append(f"'{value}'")
                        else:
                            json_set_args.append(str(value))
                
                # 无有效字段则跳过
                if len(json_set_args) == 1:
                    continue
                
                set_clause = f"ext_indicators = JSON_SET({', '.join(json_set_args)})"
                
                # 转义bond_code和time中的引号
                bond_code = str(row['bond_code']).replace("'", "''")
                time_val = str(row['time']).replace("'", "''")
                
                update_sql = f"""
                    UPDATE `{table_name}`
                    SET {set_clause}
                    WHERE bond_code = '{bond_code}' AND `time` = '{time_val}'
                """
                
                try:
                    conn.execute(text(update_sql))
                    batch_updated += 1
                except Exception as e:
                    total_failed += 1
                    if total_failed <= 5:  # 只打印前5个错误，避免刷屏
                        print(f"    [WARN] 更新失败 {bond_code} @ {time_val}: {str(e)[:80]}")
                    continue
            
            # 批次提交（释放锁）
            conn.commit()
        
        total_updated += batch_updated
        progress = min(total_updated / total_rows * 100, 100)
        elapsed = time.time() - t0
        speed = total_updated / elapsed if elapsed > 0 else 0
        print(f"    [BATCH {batch_num}/{total_batches}] 更新 {batch_updated} 行，"
              f"累计 {total_updated}/{total_rows} ({progress:.1f}%) | {speed:.0f}行/秒")
        
        # 批次间sleep，给IO和锁释放缓冲
        if batch_end < total_rows:
            time.sleep(SLEEP_SECONDS)
    
    elapsed = time.time() - t0
    speed = total_updated / elapsed if elapsed > 0 else 0
    if total_failed > 0:
        print(f"    [UPDATE] 完成，更新 {total_updated} 行，失败 {total_failed} 行，耗时 {elapsed:.1f}s, {speed:.0f}行/秒")
    else:
        print(f"    [UPDATE] 完成，更新 {total_updated} 行，耗时 {elapsed:.1f}s, {speed:.0f}行/秒")
    
    return total_updated


def _bulk_update_by_time(engine, table_name: str, updates: list, target_fields: List[str]) -> int:
    """
    【大盘指标优化】按时间点批量更新（同一时间点全市场统一值）

    适用场景：大盘指标（mkt_shape等），同一 time 下所有债券的值相同。
    每个时间点只需一条 UPDATE ... WHERE time='xxx'，一次更新该时间点的所有债券。

    对比逐行更新：4522个时间点 = 4522条SQL（替代147万条），提速数百倍。

    Args:
        engine: SQLAlchemy引擎
        table_name: 目标表名
        updates: [{time, field_values: {field: value}}]
        target_fields: 目标字段列表

    Returns:
        int: 更新的行数（累计rowcount）
    """
    if not updates:
        return 0

    import time as _time

    BATCH_SIZE = 100       # 每批时间点数（每条UPDATE影响数百行，批不宜过大）
    SLEEP_SECONDS = 0.02   # 批次间sleep，给IO和锁释放缓冲
    total_updated = 0
    total_failed = 0
    total_ticks = len(updates)
    total_batches = (total_ticks - 1) // BATCH_SIZE + 1

    for batch_start in range(0, total_ticks, BATCH_SIZE):
        batch_num = batch_start // BATCH_SIZE + 1
        batch_end = min(batch_start + BATCH_SIZE, total_ticks)
        batch = updates[batch_start:batch_end]

        with engine.connect() as conn:
            for upd in batch:
                tick_time = upd['time']
                field_values = upd['field_values']

                # 构建JSON_SET参数
                json_set_args = ["COALESCE(ext_indicators, '{}')"]
                for field in target_fields:
                    value = field_values.get(field)
                    if value is not None:
                        json_set_args.append(f"'$.{field}'")
                        if isinstance(value, str):
                            value = value.replace("'", "''")
                            json_set_args.append(f"'{value}'")
                        else:
                            json_set_args.append(str(value))

                if len(json_set_args) == 1:
                    continue

                set_clause = f"ext_indicators = JSON_SET({', '.join(json_set_args)})"
                time_val = str(tick_time).replace("'", "''")

                # 关键：WHERE time='xxx' 一次更新该时间点所有债券
                update_sql = f"""
                    UPDATE `{table_name}`
                    SET {set_clause}
                    WHERE `time` = '{time_val}'
                """

                try:
                    result = conn.execute(text(update_sql))
                    total_updated += result.rowcount
                except Exception as e:
                    total_failed += 1
                    if total_failed <= 5:
                        print(f"    [WARN] 更新失败 time={time_val}: {str(e)[:80]}")
                    continue

            # 批次提交（释放锁）
            conn.commit()

        # 批次间sleep
        if batch_end < total_ticks:
            _time.sleep(SLEEP_SECONDS)

    if total_failed > 0:
        print(f"    [UPDATE] {total_batches}批完成，更新 {total_updated:,} 行，失败 {total_failed} 个时间点")

    return total_updated


class JsonFieldBackfiller:
    """JSON字段回填引擎（字段级独立更新）"""
    
    def __init__(self, db_url=None, workers=8):
        self.db_url = db_url or DB_URL
        self.workers = workers
        self.engine = self._create_engine()
        self.json_fields = self._load_field_registry()
    
    def _create_engine(self):
        return create_engine(
            self.db_url,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
        )
    
    def _load_field_registry(self) -> Dict:
        """
        加载字段注册表
        
        从 monitor_bond.py 动态读取。
        使用与 compute_engine.py 一致的裸名导入（monitor_bond），
        确保只加载一次模块，避免重复执行模块级初始化代码。
        """
        try:
            # 使用与 compute_engine.py 相同的裸名导入，保证同一模块实例
            monitor_path = Path(__file__).parent.parent / 'src' / 'gs2026' / 'monitor'
            if str(monitor_path) not in sys.path:
                sys.path.insert(0, str(monitor_path))
            
            from monitor_bond import get_json_field_registry
            
            registry = get_json_field_registry()
            print(f"[INFO] 加载字段注册表: {list(registry.keys())}")
            return registry
            
        except Exception as e:
            print(f"[ERROR] 无法加载字段注册表: {e}")
            print(f"[ERROR]  traceback: {traceback.format_exc()}")
            return {}
    
    def get_field_def(self, name: str) -> Optional[dict]:
        """获取字段配置"""
        return self.json_fields.get(name)
    
    def get_all_dependencies(self, target_fields: List[str]) -> Set[str]:
        """获取所有依赖字段"""
        deps = set()
        for name in target_fields:
            field_def = self.get_field_def(name)
            if field_def:
                deps.update(field_def.get('depends', []))
        return deps
    
    def backfill(self, dates: List[str], target_fields: List[str], skip_existing: bool = False):
        """
        批量回填
        
        Args:
            skip_existing: True=跳过已有key的行, False=覆盖（默认）
        """
        # 验证字段
        valid_fields = []
        for name in target_fields:
            if self.get_field_def(name):
                valid_fields.append(name)
            else:
                print(f"[WARN] 未知字段: {name}")
        
        if not valid_fields:
            print("[ERROR] 没有有效的字段")
            return
        
        all_deps = self.get_all_dependencies(valid_fields)
        print(f"[BACKFILL] {len(dates)} 天, 字段: {valid_fields}")
        print(f"[BACKFILL] 依赖: {sorted(all_deps)}")
        print(f"[BACKFILL] 策略: {'跳过已有' if skip_existing else '默认覆盖'}")
        
        for date_str in dates:
            self._backfill_single_day(date_str, valid_fields, all_deps, skip_existing)
    
    def _backfill_single_day(self, date_str: str, target_fields: List[str], 
                            all_deps: Set[str], skip_existing: bool):
        """
        单日回填（流式批次版）
        
        【优化】参考 backfill_unified.py：
        - 时间分片流式读取（替代单债券查询）
        - 批次计算（向量化）
        - 批量UPDATE（临时表+UPDATE JOIN）
        - 行级进度显示
        """
        table_name = f"{TABLE_PREFIX}{date_str}"
        print(f"\n[{date_str}] 开始...")
        t0 = time.time()
        
        # 1. 预估总行数
        with self.engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
            estimated_total = result.scalar() or 0
        
        if estimated_total == 0:
            print(f"  [SKIP] 无数据")
            return
        
        print(f"  [INFO] 预估 {estimated_total:,} 行")
        
        # 2. 确定需要的列（只查询物理列，依赖字段从JSON解析）
        # 物理列：bond_code, time, ext_indicators
        # 依赖字段（如mkt_vs_open_pct）在ext_indicators JSON中
        needed_columns = {'bond_code', 'time', 'ext_indicators'}
        
        # 3. 流式读取 + 批次处理
        sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
        from compute_engine import ComputeEngine
        
        compute_engine = ComputeEngine()
        # 【优化】大盘指标同一时间点全市场统一，按时间点累积（非按债券）
        # all_updates: [{time, field_values: {field: value}}]
        all_updates = []
        FLUSH_TICKS = 500  # 每积累500个时间点刷一次
        total_ticks = 0    # 已处理的时间点数
        total_rows = 0     # 已读取的行数
        total_updated = 0  # 已更新的行数
        flush_count = 0
        
        # 预估时间点总数（用于进度）
        with self.engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(DISTINCT `time`) FROM `{table_name}`"))
            est_ticks = result.scalar() or 1
        est_flushes = max(1, est_ticks // FLUSH_TICKS)
        
        for df_batch in load_table_data_streaming(self.engine, table_name, needed_columns, 
                                                   chunk_time_count=CONFIG['DEFAULT_CHUNK_TIME_COUNT']):
            if df_batch.empty:
                continue
            
            total_rows += len(df_batch)
            
            # 4. 批次计算（大盘指标：同一时间点只需计算一次）
            for tick_time, df_tick in df_batch.groupby('time'):
                total_ticks += 1
                
                # 【优化】大盘指标全市场统一，取该时间点第一行解析依赖即可
                first_row = df_tick.iloc[0]
                ext_json = first_row['ext_indicators']
                if not ext_json:
                    continue
                
                try:
                    ext = json.loads(ext_json)
                except:
                    ext = {}
                
                # 检查skip_existing（该时间点已有目标字段则跳过，但仍需更新状态）
                if skip_existing and all(f in ext for f in target_fields):
                    deps = {dep: ext.get(dep) for dep in all_deps}
                    compute_engine._update_state(deps)
                    continue
                
                # 提取依赖 + 更新状态
                deps = {dep: ext.get(dep) for dep in all_deps}
                compute_engine._update_state(deps)
                
                # 计算目标字段
                field_values = {}
                for field_name in target_fields:
                    field_config = self.json_fields.get(field_name)
                    if not field_config:
                        continue
                    
                    # 构建历史
                    history = []
                    if field_config.get('needs_history'):
                        state_var = field_config.get('state_vars', [''])[0].lstrip('_')
                        history = getattr(compute_engine, state_var, [])
                        history = history[:-1] if len(history) > 1 else []
                    
                    # 计算
                    value = compute_engine._compute_json_field(field_name, deps, history)
                    field_values[field_name] = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
                
                if field_values:
                    all_updates.append({
                        'time': str(tick_time),
                        'field_values': field_values,
                    })
            
            # 5. 达到批次阈值，执行按时间点批量UPDATE
            if len(all_updates) >= FLUSH_TICKS:
                updated = _bulk_update_by_time(self.engine, table_name, all_updates, target_fields)
                total_updated += updated
                all_updates = []
                flush_count += 1
                
                # 打印进度
                elapsed = time.time() - t0
                progress = total_ticks / est_ticks * 100 if est_ticks > 0 else 0
                speed = total_ticks / elapsed if elapsed > 0 else 0
                remaining = (est_ticks - total_ticks) / speed if speed > 0 else 0
                print(f"  [{date_str} #{flush_count}/~{est_flushes}] "
                      f"{total_ticks:,}/{est_ticks:,} 时间点 ({progress:.1f}%) | "
                      f"{total_updated:,} 行更新 | 剩余 {remaining:.0f}s")
        
        # 6. 写入剩余数据
        if all_updates:
            updated = _bulk_update_by_time(self.engine, table_name, all_updates, target_fields)
            total_updated += updated
        
        elapsed = time.time() - t0
        print(f"  [DONE] {total_ticks:,} 时间点处理, {total_updated:,} 行更新, "
              f"耗时 {elapsed:.1f}s")


def cleanup_zombie_transactions(engine, table_prefix: str):
    """
    启动前清理僵尸事务和遗留临时表
    
    防止上次异常退出留下的长事务持有锁，导致后续UPDATE超时。
    - 杀掉执行时间>120s且操作目标表的Query
    - 删除遗留的 _temp_json% 临时表
    """
    try:
        # 1. 杀掉僵尸事务（执行超过120秒且操作监控表）
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id, time, LEFT(info, 60) as info
                FROM information_schema.processlist
                WHERE command IN ('Query', 'Execute')
                  AND time > 120
                  AND info LIKE '%{table_prefix}%'
            """))
            zombies = list(result)
        
        if zombies:
            with engine.connect() as conn:
                for row in zombies:
                    pid = row[0]
                    try:
                        conn.execute(text(f"KILL {pid}"))
                        print(f"[CLEANUP] 杀掉僵尸事务 ID={pid} (运行{row[1]}s)")
                    except Exception:
                        pass
                conn.commit()
        
        # 2. 删除遗留临时表
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = DATABASE() AND table_name LIKE '_temp_json%'
            """))
            temp_tables = [row[0] for row in result]
        
        if temp_tables:
            with engine.connect() as conn:
                for t in temp_tables:
                    try:
                        conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))
                    except Exception:
                        pass
                conn.commit()
            print(f"[CLEANUP] 清理 {len(temp_tables)} 个遗留临时表")
    
    except Exception as e:
        print(f"[CLEANUP] 清理检查失败（不影响主流程）: {str(e)[:80]}")


def main():
    parser = argparse.ArgumentParser(description='JSON字段快速回填（字段级独立更新）')
    parser.add_argument('--date', help='单日 YYYYMMDD')
    parser.add_argument('--start', default=CONFIG['DEFAULT_START'], help=f'开始日期（默认: {CONFIG["DEFAULT_START"]}）')
    parser.add_argument('--end', default=CONFIG['DEFAULT_END'], help=f'结束日期（默认: {CONFIG["DEFAULT_END"]}）')
    parser.add_argument('--fields', nargs='+', default=CONFIG['DEFAULT_FIELDS'], 
                       help=f'目标字段（默认: {CONFIG["DEFAULT_FIELDS"]}）')
    parser.add_argument('--skip-existing', action='store_true', default=CONFIG['DEFAULT_SKIP_EXISTING'],
                       help=f'跳过已有key的行（默认: {CONFIG["DEFAULT_SKIP_EXISTING"]}）')
    parser.add_argument('--workers', type=int, default=CONFIG['DEFAULT_WORKERS'], 
                       help=f'并行数（默认: {CONFIG["DEFAULT_WORKERS"]}）')
    parser.add_argument('--backup', action='store_true', default=CONFIG['DEFAULT_BACKUP'],
                       help=f'启用备份模式（默认: {CONFIG["DEFAULT_BACKUP"]}）')
    args = parser.parse_args()
    
    # 日期范围
    if args.date:
        dates = [args.date]
    else:
        # 生成日期范围内的所有日期（简化处理，不查询交易日历）
        from datetime import timedelta
        start_dt = datetime.strptime(args.start, '%Y%m%d')
        end_dt = datetime.strptime(args.end, '%Y%m%d')
        dates = []
        current = start_dt
        while current <= end_dt:
            dates.append(current.strftime('%Y%m%d'))
            current += timedelta(days=1)
        
        # 可选：过滤掉周末（周六=5, 周日=6）
        dates = [d for d in dates if datetime.strptime(d, '%Y%m%d').weekday() < 5]
    
    if not dates:
        print("[ERROR] 没有有效的日期")
        return
    
    # 【优化】并行度自动调整：实际并行度 = min(日期数量, 设置并行度)
    actual_workers = min(len(dates), args.workers)
    if actual_workers != args.workers:
        print(f"[INFO] 自动调整并行度: {args.workers} -> {actual_workers} (日期数: {len(dates)})")
    
    # 【防护】启动前清理僵尸事务和遗留临时表（防止上次异常退出留下的长事务持有锁）
    _cleanup_engine = create_engine(DB_URL)
    cleanup_zombie_transactions(_cleanup_engine, TABLE_PREFIX)
    _cleanup_engine.dispose()
    
    # 备份模式
    if args.backup:
        print(f"[BACKUP] 启用备份模式")
        for date_str in dates:
            table_name = f"{TABLE_PREFIX}{date_str}"
            backup_name = f"{table_name}_backup"
            try:
                engine = create_engine(DB_URL)
                with engine.connect() as conn:
                    # 检查原表是否存在
                    result = conn.execute(text(f"""
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = DATABASE() AND table_name = '{table_name}'
                    """))
                    if not result.fetchone():
                        print(f"[WARN] 表不存在: {table_name}")
                        continue
                    
                    # 检查备份表是否已存在
                    result = conn.execute(text(f"""
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = DATABASE() AND table_name = '{backup_name}'
                    """))
                    if result.fetchone():
                        print(f"[BACKUP] 备份表已存在，跳过: {backup_name}")
                    else:
                        # 创建备份表
                        conn.execute(text(f"CREATE TABLE `{backup_name}` AS SELECT * FROM `{table_name}`"))
                        conn.commit()
                        print(f"[BACKUP] {table_name} -> {backup_name}")
                engine.dispose()
            except Exception as e:
                print(f"[ERROR] 备份失败 {table_name}: {e}")
                return
    
    # 执行
    backfiller = JsonFieldBackfiller(workers=actual_workers)
    backfiller.backfill(dates, args.fields, args.skip_existing)
    print("\n[COMPLETE] 完成")
    
    # 提示恢复命令
    if args.backup:
        print("\n[BACKUP] 如需恢复数据，请执行：")
        for date_str in dates:
            table_name = f"{TABLE_PREFIX}{date_str}"
            backup_name = f"{table_name}_backup"
            print(f"  mysql -e \"DROP TABLE {table_name}; RENAME TABLE {backup_name} TO {table_name};\"")


if __name__ == '__main__':
    main()
