"""
回填 min1_change_pct / min1_amount 到 MySQL 和/或 Redis
按债券代码逐个处理，每完成一个债券输出进度

用法:
  python backfill_min1_final.py [日期] --mysql    # 仅MySQL
  python backfill_min1_final.py [日期] --redis    # 仅Redis（需MySQL已有min1数据）
  python backfill_min1_final.py [日期] --all      # 全部（默认）

示例:
  python backfill_min1_final.py 20260706 --mysql
  python backfill_min1_final.py 20260706 --redis
  python backfill_min1_final.py --all
"""
import sys
import time as time_mod

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config
import pandas as pd

# ====== 参数解析 ======
args = sys.argv[1:]
date = '20260706'
mode = 'redis'

for arg in args:
    if arg.startswith('--'):
        mode = arg[2:]  # mysql / redis / all
    elif arg.isdigit() and len(arg) == 8:
        date = arg

table = f"monitor_zq_sssj_{date}"
EXPIRE_SECONDS = 7200  # 2小时

engine = create_engine(Config.MYSQL_URI, pool_pre_ping=True,
                       connect_args={'connect_timeout': 10, 'read_timeout': 120, 'write_timeout': 120})

print(f"{'='*60}")
print(f"回填 min1 字段: {table}")
print(f"模式: {mode}")
print(f"{'='*60}")

# ====================================================================
# MySQL 模式
# ====================================================================
def run_mysql():
    print(f"\n[MySQL] 开始...")

    # 确保列存在
    with engine.connect() as conn:
        cols = [c[0] for c in conn.execute(text(f"SHOW COLUMNS FROM {table}")).fetchall()]
        if 'min1_change_pct' not in cols:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN min1_change_pct DOUBLE DEFAULT NULL"))
            conn.commit()
            print("  + 已添加 min1_change_pct 列")
        if 'min1_amount' not in cols:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN min1_amount DOUBLE DEFAULT NULL"))
            conn.commit()
            print("  + 已添加 min1_amount 列")

    # 获取所有债券代码
    with engine.connect() as conn:
        bonds = [r[0] for r in conn.execute(text(
            f"SELECT DISTINCT bond_code FROM {table} ORDER BY bond_code"
        )).fetchall()]
    print(f"  债券总数: {len(bonds)}")

    start_time = time_mod.time()
    mysql_updated = 0
    errors = 0

    for idx, bond_code in enumerate(bonds):
        try:
            with engine.connect() as conn:
                # 查询该债券所有记录
                df = pd.read_sql(text(
                    f"SELECT bond_code, time, change_pct, amount FROM {table} "
                    f"WHERE bond_code = :code ORDER BY time"
                ), conn, params={'code': bond_code})

                if df.empty:
                    continue

                # 按分钟分组计算 min1
                df['minute'] = df['time'].str[:5]
                first_per_min = df.groupby('minute').first()[['change_pct', 'amount']].to_dict('index')

                min1_pcts = []
                min1_amts = []
                for _, row in df.iterrows():
                    base = first_per_min.get(row['minute'], {})
                    base_pct = base.get('change_pct', row['change_pct'])
                    base_amt = base.get('amount', row['amount'])

                    m1_pct = round(row['change_pct'] - base_pct, 4) if pd.notna(row['change_pct']) and pd.notna(base_pct) else 0.0
                    m1_amt = round(row['amount'] - base_amt, 0) if pd.notna(row['amount']) and pd.notna(base_amt) else 0.0

                    min1_pcts.append(m1_pct)
                    min1_amts.append(m1_amt)

                df['min1_change_pct'] = min1_pcts
                df['min1_amount'] = min1_amts

                # 批量更新MySQL（CASE WHEN）
                batch_size = 200
                for start in range(0, len(df), batch_size):
                    batch = df.iloc[start:start + batch_size]
                    cases_pct = ""
                    cases_amt = ""
                    times_list = []
                    for _, row in batch.iterrows():
                        t = row['time']
                        cases_pct += f" WHEN time='{t}' THEN {row['min1_change_pct']}"
                        cases_amt += f" WHEN time='{t}' THEN {row['min1_amount']}"
                        times_list.append(f"'{t}'")

                    sql = f"""
                        UPDATE {table}
                        SET min1_change_pct = CASE {cases_pct} END,
                            min1_amount = CASE {cases_amt} END
                        WHERE bond_code = '{bond_code}' AND time IN ({','.join(times_list)})
                    """
                    conn.execute(text(sql))

                conn.commit()
                mysql_updated += len(df)

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  [ERROR] {bond_code}: {e}")
            continue

        # 进度日志
        if (idx + 1) % 50 == 0 or (idx + 1) == len(bonds):
            elapsed = time_mod.time() - start_time
            speed = (idx + 1) / elapsed if elapsed > 0 else 0
            eta = (len(bonds) - idx - 1) / speed if speed > 0 else 0
            print(f"  [MySQL] {idx+1}/{len(bonds)} 债券 | {mysql_updated} 行 | "
                  f"{speed:.1f} 债/s | ETA {eta:.0f}s | 失败 {errors}")

    print(f"\n[MySQL] 完成! 更新 {mysql_updated} 行, 失败 {errors}, 耗时 {time_mod.time()-start_time:.1f}s")


# ====================================================================
# Redis 模式（从MySQL读取已计算的min1数据，写入Redis）
# ====================================================================
def run_redis():
    print(f"\n[Redis] 开始...")

    # 初始化 Redis 连接
    from gs2026.utils import redis_util
    redis_util.init_redis(host='localhost', port=6379, db=0)
    print("  Redis 已初始化")

    # 获取所有时间点
    with engine.connect() as conn:
        time_points = [r[0] for r in conn.execute(text(
            f"SELECT DISTINCT time FROM {table} ORDER BY time"
        )).fetchall()]
    print(f"  时间点数: {len(time_points)}")

    start_time = time_mod.time()
    redis_done = 0
    redis_skip = 0
    redis_errors = 0

    for i, time_str in enumerate(time_points):
        try:
            # 从MySQL读取该时间点的完整数据（含min1字段）
            with engine.connect() as conn:
                df = pd.read_sql(text(
                    f"SELECT * FROM {table} WHERE time = :t"
                ), conn, params={'t': time_str})

            if df.empty:
                redis_skip += 1
                continue

            # 直接写入Redis（覆盖原有数据）
            redis_util.save_dataframe_to_redis(df, table, time_str, EXPIRE_SECONDS)
            redis_done += 1

        except Exception as e:
            redis_errors += 1
            if redis_errors <= 5:
                print(f"  [Redis ERROR] {time_str}: {e}")
            continue

        # 进度日志
        if (i + 1) % 3 == 0 or (i + 1) == len(time_points):
            elapsed = time_mod.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(time_points) - i - 1) / speed if speed > 0 else 0
            print(f"  [Redis] {i+1}/{len(time_points)} 时间点 | 写入 {redis_done} | "
                  f"{speed:.1f} 点/s | ETA {eta:.0f}s")

    print(f"\n[Redis] 完成! 写入 {redis_done}, 跳过 {redis_skip}, 失败 {redis_errors}, "
          f"耗时 {time_mod.time()-start_time:.1f}s")


# ====================================================================
# 验证
# ====================================================================
def verify():
    print(f"\n{'='*60}")
    print("[验证]")
    with engine.connect() as conn:
        stats = conn.execute(text(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN min1_change_pct IS NOT NULL AND min1_change_pct != 0 THEN 1 ELSE 0 END) as non_zero
            FROM {table}
        """)).fetchone()
        print(f"  MySQL 总行数: {stats[0]}, 非零min1: {stats[1]}")

        sample = conn.execute(text(f"""
            SELECT bond_code, time, change_pct, min1_change_pct, amount, min1_amount
            FROM {table}
            WHERE min1_change_pct IS NOT NULL AND min1_change_pct != 0
            ORDER BY ABS(min1_change_pct) DESC LIMIT 5
        """)).fetchall()
        if sample:
            print("  Top5 min1_change_pct:")
            for r in sample:
                print(f"    {r[0]} {r[1]} | pct={r[2]:.4f} min1_pct={r[3]:.4f} | amt={r[4]:.0f} min1_amt={r[5]:.0f}")
        else:
            print("  ⚠️ 无非零min1数据（可能MySQL还未回填）")


# ====================================================================
# 主入口
# ====================================================================
if __name__ == '__main__':
    total_start = time_mod.time()

    if mode in ('mysql', 'all'):
        run_mysql()

    if mode in ('redis', 'all'):
        run_redis()

    verify()

    print(f"\n{'='*60}")
    print(f"✅ 全部完成! 模式={mode}, 总耗时 {time_mod.time()-total_start:.1f}s")
    print(f"{'='*60}")
