"""
回填 amount_rank 字段到债券sssj表
按时间点逐个处理，每完成一批输出进度

用法: python backfill_amount_rank.py [dates...]
示例: python backfill_amount_rank.py 20260706 20260707 20260708
"""
import sys
import time as time_mod

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI, pool_pre_ping=True)


def backfill_table(date_str):
    table = f"monitor_zq_sssj_{date_str}"
    print(f"\n{'='*60}")
    print(f"[{date_str}] 处理表: {table}")
    print(f"{'='*60}")

    with engine.connect() as conn:
        # 1. 检查表是否存在
        result = conn.execute(text(f"SHOW TABLES LIKE '{table}'")).fetchone()
        if not result:
            print(f"  ⚠️ 表不存在，跳过")
            return False

        # 2. 检查列是否已存在，不存在则添加
        cols = conn.execute(text(f"SHOW COLUMNS FROM {table} LIKE 'amount_rank'")).fetchone()
        if not cols:
            print(f"  添加列 amount_rank INT...")
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN `amount_rank` INT DEFAULT NULL"))
            conn.commit()
            print(f"  ✅ 列已添加")
        else:
            # 检查是否已有数据
            filled = conn.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE amount_rank IS NOT NULL"
            )).scalar()
            total_rows = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            if filled == total_rows and filled > 0:
                print(f"  ✅ 已全部填充 ({filled} 行)，跳过")
                return True
            print(f"  列已存在，已填充 {filled}/{total_rows} 行，继续回填...")

        # 3. 获取所有时间点
        times = conn.execute(text(
            f"SELECT DISTINCT time FROM {table} ORDER BY time"
        )).fetchall()
        total_tp = len(times)
        print(f"  共 {total_tp} 个时间点")

        # 4. 获取总行数
        total_rows = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        print(f"  共 {total_rows:,} 行数据")
        print(f"  开始计算金额排名...\n")

        # 5. 逐时间点计算排名并更新
        start_time = time_mod.time()
        updated_rows = 0
        errors = 0

        for idx, (t,) in enumerate(times):
            time_str = str(t)
            try:
                # 单个时间点内按amount降序排名
                sql = text(f"""
                    UPDATE {table} t
                    INNER JOIN (
                        SELECT bond_code,
                               RANK() OVER (ORDER BY amount DESC) as amt_rank
                        FROM {table}
                        WHERE time = :time_val
                    ) ranked ON t.bond_code = ranked.bond_code
                    SET t.amount_rank = ranked.amt_rank
                    WHERE t.time = :time_val
                """)
                result = conn.execute(sql, {'time_val': time_str})
                updated_rows += result.rowcount

            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  [ERROR] time={time_str}: {e}")
                continue

            # 每50个时间点提交一次 + 输出进度
            if (idx + 1) % 50 == 0 or (idx + 1) == total_tp:
                conn.commit()
                elapsed = time_mod.time() - start_time
                speed = (idx + 1) / elapsed if elapsed > 0 else 0
                eta = (total_tp - idx - 1) / speed if speed > 0 else 0
                pct = (idx + 1) / total_tp * 100
                print(f"  [{date_str}] {idx+1}/{total_tp} 时间点 ({pct:.1f}%) | "
                      f"{updated_rows:,} 行 | {speed:.1f} tp/s | "
                      f"耗时 {elapsed:.0f}s | ETA {eta:.0f}s | 失败 {errors}")

        conn.commit()
        elapsed = time_mod.time() - start_time
        print(f"\n  ✅ [{date_str}] 完成! "
              f"{total_tp} 时间点 | {updated_rows:,} 行已更新 | "
              f"失败 {errors} | 总耗时 {elapsed:.1f}s")
        return True


if __name__ == '__main__':
    dates = sys.argv[1:] if len(sys.argv) > 1 else ['20260701', '20260702', '20260703']

    print(f"{'='*60}")
    print(f"回填 amount_rank (金额排名) 字段")
    print(f"目标日期: {', '.join(dates)}")
    print(f"{'='*60}")

    total_start = time_mod.time()
    success = 0

    for d in dates:
        if backfill_table(d):
            success += 1

    print(f"\n{'='*60}")
    print(f"全部完成! 成功 {success}/{len(dates)} 个表, "
          f"总耗时 {time_mod.time()-total_start:.1f}s")
    print(f"{'='*60}")
