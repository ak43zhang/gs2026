"""
统一回填脚本（高性能版）：一次性回填 sssj 表所有增量计算字段

优化点（vs旧版）：
  1. 用 executemany 批量UPDATE（原来逐行execute，320行→1次调用）
  2. 累积多个时间点后统一提交（减少commit次数）
  3. 预估提速 10-30x

回填字段:
  min1_change_pct, min1_amount, amount_rank,
  slope_short, slope_long, peak_vol_bias, high_distance

用法:
  python backfill_all_fields.py [dates...]
  python backfill_all_fields.py 20260706 20260707 20260708
"""
import sys
import time as time_mod
from collections import deque

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.dashboard2.config import Config

engine = create_engine(
    Config.MYSQL_URI,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=0,
)

# ====== 常量 ======
WINDOW_SHORT = 60
WINDOW_LONG = 300
COMMIT_BATCH = 20  # 每20个时间点提交一次（~6400行/批）

NEW_COLUMNS = [
    ('min1_change_pct', 'DOUBLE DEFAULT NULL'),
    ('min1_amount', 'DOUBLE DEFAULT NULL'),
    ('amount_rank', 'INT DEFAULT NULL'),
    ('slope_short', 'DOUBLE DEFAULT NULL'),
    ('slope_long', 'DOUBLE DEFAULT NULL'),
    ('peak_vol_bias', 'DOUBLE DEFAULT NULL'),
    ('high_distance', 'DOUBLE DEFAULT NULL'),
    ('mkt_slope_short', 'DOUBLE DEFAULT NULL'),
    ('mkt_slope_long', 'DOUBLE DEFAULT NULL'),
    ('mkt_peak_vol_bias', 'DOUBLE DEFAULT NULL'),
    ('mkt_high_distance', 'DOUBLE DEFAULT NULL'),
]


def calc_slope(buf):
    """线性回归斜率"""
    n = len(buf)
    if n < 3:
        return 0.0
    sum_x = n * (n - 1) / 2
    sum_x2 = n * (n - 1) * (2 * n - 1) / 6
    sum_y = 0.0
    sum_xy = 0.0
    for i, y in enumerate(buf):
        sum_y += y
        sum_xy += i * y
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def backfill_table(date_str):
    table = f"monitor_zq_sssj_{date_str}"
    print(f"\n{'='*70}")
    print(f"[{date_str}] 统一回填: {table}")
    print(f"{'='*70}")

    conn = engine.raw_connection()
    cursor = conn.cursor()

    try:
        # 1. 检查表是否存在
        cursor.execute(f"SHOW TABLES LIKE '{table}'")
        if not cursor.fetchone():
            print(f"  ⚠️ 表不存在，跳过")
            return False

        # 2. 添加缺失列
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        existing_cols = {row[0] for row in cursor.fetchall()}
        added = []
        for col_name, col_def in NEW_COLUMNS:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN `{col_name}` {col_def}")
                added.append(col_name)
        if added:
            conn.commit()
            print(f"  新增列: {', '.join(added)}")
        else:
            print(f"  所有列已存在")

        # 3. 获取所有时间点
        cursor.execute(f"SELECT DISTINCT time FROM {table} ORDER BY time")
        times = [row[0] for row in cursor.fetchall()]
        total_tp = len(times)

        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total_rows = cursor.fetchone()[0]
        print(f"  共 {total_tp} 个时间点, {total_rows:,} 行")
        print(f"  提交批次: 每 {COMMIT_BATCH} 个时间点")
        print(f"  开始回填...\n")

        # 4. 初始化增量状态
        min1_base_minute = None
        min1_base_pct = {}
        min1_base_amt = {}
        slope_buf_short = {}
        slope_buf_long = {}
        peak_vol_state = {}
        high_state = {}
        # 大盘级缓存
        mkt_slope_buf_short = deque(maxlen=WINDOW_SHORT)
        mkt_slope_buf_long = deque(maxlen=WINDOW_LONG)
        mkt_peak_vol = {'max_total_amt': 0, 'pct_at_max': 0.0}
        mkt_high = {'max_avg_pct': -999.0}

        # 准备UPDATE SQL（使用raw cursor的executemany）
        update_sql = f"""
            UPDATE {table}
            SET min1_change_pct=%s, min1_amount=%s, amount_rank=%s,
                slope_short=%s, slope_long=%s, peak_vol_bias=%s, high_distance=%s,
                mkt_slope_short=%s, mkt_slope_long=%s, mkt_peak_vol_bias=%s, mkt_high_distance=%s
            WHERE bond_code=%s AND time=%s
        """

        start_time = time_mod.time()
        updated_rows = 0
        errors = 0
        batch_params = []

        # 5. 逐时间点处理
        for idx, t in enumerate(times):
            time_str = str(t)
            current_minute = time_str[:5]

            try:
                # 加载该时间点数据
                cursor.execute(
                    f"SELECT bond_code, change_pct, price, amount FROM {table} WHERE time = %s",
                    (time_str,)
                )
                rows = cursor.fetchall()
                if not rows:
                    continue

                codes = [r[0] for r in rows]
                change_pcts = [float(r[1]) for r in rows]
                prices = [float(r[2]) for r in rows]
                amounts = [float(r[3]) for r in rows]

                # ---- 大盘指标（市场级，每时间点一组）----
                avg_pct = sum(change_pcts) / len(change_pcts) if change_pcts else 0
                total_amt = sum(amounts)

                mkt_slope_buf_short.append(avg_pct)
                mkt_ss = round(calc_slope(mkt_slope_buf_short), 6)

                mkt_slope_buf_long.append(avg_pct)
                mkt_sl = round(calc_slope(mkt_slope_buf_long), 6)

                if total_amt > mkt_peak_vol['max_total_amt']:
                    mkt_peak_vol['max_total_amt'] = total_amt
                    mkt_peak_vol['pct_at_max'] = avg_pct
                mkt_pvb = round(avg_pct - mkt_peak_vol['pct_at_max'], 4)

                if avg_pct > mkt_high['max_avg_pct']:
                    mkt_high['max_avg_pct'] = avg_pct
                mkt_hd = round(avg_pct - mkt_high['max_avg_pct'], 4)

                # ---- min1 ----
                if min1_base_minute != current_minute:
                    min1_base_pct = dict(zip(codes, change_pcts))
                    min1_base_amt = dict(zip(codes, amounts))
                    min1_base_minute = current_minute

                # ---- 逐bond计算 ----
                # amount排名（批量）
                sorted_indices = sorted(range(len(amounts)), key=lambda i: amounts[i], reverse=True)
                amount_ranks = [0] * len(amounts)
                for rank, si in enumerate(sorted_indices, 1):
                    amount_ranks[si] = rank

                for i in range(len(codes)):
                    code = codes[i]
                    cpct = change_pcts[i]
                    price = prices[i]
                    amount = amounts[i]

                    # min1
                    m1c = round(cpct - min1_base_pct.get(code, cpct), 4)
                    m1a = round(amount - min1_base_amt.get(code, amount), 0)

                    # slope_short
                    if code not in slope_buf_short:
                        slope_buf_short[code] = deque(maxlen=WINDOW_SHORT)
                    slope_buf_short[code].append(cpct)
                    ss = round(calc_slope(slope_buf_short[code]), 6)

                    # slope_long
                    if code not in slope_buf_long:
                        slope_buf_long[code] = deque(maxlen=WINDOW_LONG)
                    slope_buf_long[code].append(cpct)
                    sl = round(calc_slope(slope_buf_long[code]), 6)

                    # peak_vol_bias
                    if code not in peak_vol_state:
                        peak_vol_state[code] = {'max_amount': 0, 'price_at_max': price}
                    pv = peak_vol_state[code]
                    if amount > pv['max_amount']:
                        pv['max_amount'] = amount
                        pv['price_at_max'] = price
                    pvb = round((price - pv['price_at_max']) / pv['price_at_max'] * 100, 4) if pv['price_at_max'] > 0 else 0

                    # high_distance
                    if code not in high_state:
                        high_state[code] = {'max_cpct': cpct}
                    hs = high_state[code]
                    if cpct > hs['max_cpct']:
                        hs['max_cpct'] = cpct
                    hd = round(cpct - hs['max_cpct'], 4)

                    # 累积参数
                    batch_params.append((m1c, m1a, amount_ranks[i], ss, sl, pvb, hd, mkt_ss, mkt_sl, mkt_pvb, mkt_hd, code, time_str))

                updated_rows += len(codes)

            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  [ERROR] time={time_str}: {e}")
                continue

            # 批量提交
            if (idx + 1) % COMMIT_BATCH == 0 or (idx + 1) == total_tp:
                if batch_params:
                    cursor.executemany(update_sql, batch_params)
                    conn.commit()
                    batch_params = []

                elapsed = time_mod.time() - start_time
                speed = (idx + 1) / elapsed if elapsed > 0 else 0
                eta = (total_tp - idx - 1) / speed if speed > 0 else 0
                pct = (idx + 1) / total_tp * 100
                print(f"  [{date_str}] {idx+1}/{total_tp} ({pct:.1f}%) | "
                      f"{updated_rows:,} 行 | {speed:.1f} tp/s | "
                      f"耗时 {elapsed:.0f}s | ETA {eta:.0f}s | 失败 {errors}")

        # 最终提交
        if batch_params:
            cursor.executemany(update_sql, batch_params)
            conn.commit()

        elapsed = time_mod.time() - start_time
        print(f"\n  ✅ [{date_str}] 完成! "
              f"{total_tp} 时间点 | {updated_rows:,} 行 | "
              f"失败 {errors} | 总耗时 {elapsed:.1f}s")
        return True

    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    dates = sys.argv[1:] if len(sys.argv) > 1 else ['20260629', '20260630'] #

    print(f"{'='*70}")
    print(f"统一回填(高性能版): min1 + rank + slope + peak_vol_bias + high_distance")
    print(f"目标日期: {', '.join(dates)}")
    print(f"优化: executemany批量 + {COMMIT_BATCH}tp/批提交")
    print(f"{'='*70}")

    total_start = time_mod.time()
    success = 0

    for d in dates:
        if backfill_table(d):
            success += 1

    print(f"\n{'='*70}")
    print(f"全部完成! 成功 {success}/{len(dates)} 个表, "
          f"总耗时 {time_mod.time()-total_start:.1f}s")
    print(f"{'='*70}")
