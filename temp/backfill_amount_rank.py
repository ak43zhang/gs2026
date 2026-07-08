"""
回填 amount_rank 字段到债券sssj表
用法: python backfill_amount_rank.py [dates...]
示例: python backfill_amount_rank.py 20260706 20260707 20260708
"""
import sys
import time
from sqlalchemy import create_engine, text

# 数据库配置（与项目一致）
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI, pool_pre_ping=True)


def backfill_table(date_str):
    table = f"monitor_zq_sssj_{date_str}"
    print(f"\n{'='*60}")
    print(f"[{date_str}] 处理表: {table}")

    with engine.connect() as conn:
        # 1. 检查表是否存在
        result = conn.execute(text(f"SHOW TABLES LIKE '{table}'")).fetchone()
        if not result:
            print(f"  ⚠️ 表不存在，跳过")
            return

        # 2. 检查列是否已存在
        cols = conn.execute(text(f"SHOW COLUMNS FROM {table} LIKE 'amount_rank'")).fetchone()
        if not cols:
            print(f"  添加列 amount_rank...")
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN `amount_rank` INT DEFAULT NULL"))
            conn.commit()
            print(f"  ✅ 列已添加")
        else:
            print(f"  列已存在")

        # 3. 获取所有时间点
        times = conn.execute(text(f"SELECT DISTINCT time FROM {table} ORDER BY time")).fetchall()
        total = len(times)
        print(f"  共 {total} 个时间点，开始计算排名...")

        # 4. 分批更新（每个时间点独立事务，避免长锁）
        start = time.time()
        for i, (t,) in enumerate(times):
            time_str = str(t)
            # 使用子查询计算排名并更新
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
            conn.execute(sql, {'time_val': time_str})

            # 每100个时间点提交一次
            if (i + 1) % 100 == 0:
                conn.commit()
                elapsed = time.time() - start
                speed = (i + 1) / elapsed
                eta = (total - i - 1) / speed
                print(f"  进度: {i+1}/{total} ({(i+1)/total*100:.1f}%) | 速度: {speed:.1f} tp/s | ETA: {eta:.0f}s")

        conn.commit()
        elapsed = time.time() - start
        print(f"  ✅ 完成! 共{total}个时间点, 耗时{elapsed:.1f}s")


if __name__ == '__main__':
    dates = sys.argv[1:] if len(sys.argv) > 1 else ['20260706', '20260707', '20260708']
    print(f"回填 amount_rank 字段，目标日期: {dates}")

    for d in dates:
        backfill_table(d)

    print(f"\n{'='*60}")
    print("全部完成!")
