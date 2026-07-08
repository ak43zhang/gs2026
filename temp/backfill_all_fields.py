"""
统一回填脚本：一次性回填 sssj 表所有增量计算字段

回填字段:
  - min1_change_pct  (1分钟涨幅变化)
  - min1_amount      (1分钟金额变化)
  - amount_rank      (金额排名)
  - slope_short      (3分钟滚动斜率)
  - slope_long       (15分钟滚动斜率)
  - peak_vol_bias    (放量高点偏离%)
  - high_distance    (日内高点距离%)

用法:
  python backfill_all_fields.py [dates...]
  python backfill_all_fields.py 20260706 20260707 20260708

说明:
  - 按时间顺序逐时间点处理，模拟实时采集流程
  - 保证计算口径与实时采集完全一致
  - 每50个时间点提交一次 + 输出进度
"""
import sys
import time as time_mod
from collections import deque

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.dashboard2.config import Config

engine = create_engine(Config.MYSQL_URI, pool_pre_ping=True)

# ====== 常量 ======
WINDOW_SHORT = 60
WINDOW_LONG = 300
NEW_COLUMNS = [
    ('min1_change_pct', 'DOUBLE DEFAULT NULL'),
    ('min1_amount', 'DOUBLE DEFAULT NULL'),
    ('amount_rank', 'INT DEFAULT NULL'),
    ('slope_short', 'DOUBLE DEFAULT NULL'),
    ('slope_long', 'DOUBLE DEFAULT NULL'),
    ('peak_vol_bias', 'DOUBLE DEFAULT NULL'),
    ('high_distance', 'DOUBLE DEFAULT NULL'),
]


# ====== 斜率计算 ======
def calc_slope(buf):
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

    with engine.connect() as conn:
        # 1. 检查表是否存在
        result = conn.execute(text(f"SHOW TABLES LIKE '{table}'")).fetchone()
        if not result:
            print(f"  ⚠️ 表不存在，跳过")
            return False

        # 2. 添加缺失列
        existing_cols = set()
        for row in conn.execute(text(f"SHOW COLUMNS FROM {table}")).fetchall():
            existing_cols.add(row[0])

        added = []
        for col_name, col_def in NEW_COLUMNS:
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN `{col_name}` {col_def}"))
                added.append(col_name)
        if added:
            conn.commit()
            print(f"  新增列: {', '.join(added)}")
        else:
            print(f"  所有列已存在")

        # 3. 获取所有时间点
        times = conn.execute(text(
            f"SELECT DISTINCT time FROM {table} ORDER BY time"
        )).fetchall()
        total_tp = len(times)

        total_rows = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        print(f"  共 {total_tp} 个时间点, {total_rows:,} 行")
        print(f"  开始回填所有字段...\n")

    # 4. 初始化增量状态
    min1_base_minute = None
    min1_base_pct = {}
    min1_base_amt = {}
    slope_buf_short = {}  # { code: deque }
    slope_buf_long = {}
    peak_vol_state = {}   # { code: {'max_amount', 'price_at_max'} }
    high_state = {}       # { code: {'max_cpct'} }

    start_time = time_mod.time()
    updated_rows = 0
    errors = 0

    # 5. 逐时间点处理
    for idx, (t,) in enumerate(times):
        time_str = str(t)
        current_minute = time_str[:5]  # 'HH:MM'

        try:
            # 加载该时间点数据
            with engine.connect() as conn:
                df = pd.read_sql(text(
                    f"SELECT bond_code, change_pct, price, amount FROM {table} WHERE time = :t"
                ), conn, params={'t': time_str})

            if df.empty:
                continue

            # ---- min1 计算 ----
            if min1_base_minute != current_minute:
                min1_base_pct = dict(zip(df['bond_code'], df['change_pct']))
                min1_base_amt = dict(zip(df['bond_code'], df['amount']))
                min1_base_minute = current_minute

            base_pct = df['bond_code'].map(min1_base_pct).fillna(df['change_pct'])
            base_amt = df['bond_code'].map(min1_base_amt).fillna(df['amount'])
            df['min1_change_pct'] = (df['change_pct'] - base_pct).round(4)
            df['min1_amount'] = (df['amount'] - base_amt).round(0)

            # ---- amount_rank ----
            df['amount_rank'] = df['amount'].rank(ascending=False, method='min').astype(int)

            # ---- slope + peak_vol_bias + high_distance ----
            slopes_s = []
            slopes_l = []
            biases = []
            high_dists = []

            for _, row in df.iterrows():
                code = row['bond_code']
                cpct = float(row['change_pct'])
                price = float(row['price'])
                amount = float(row['amount'])

                # slope_short
                if code not in slope_buf_short:
                    slope_buf_short[code] = deque(maxlen=WINDOW_SHORT)
                slope_buf_short[code].append(cpct)
                slopes_s.append(round(calc_slope(slope_buf_short[code]), 6))

                # slope_long
                if code not in slope_buf_long:
                    slope_buf_long[code] = deque(maxlen=WINDOW_LONG)
                slope_buf_long[code].append(cpct)
                slopes_l.append(round(calc_slope(slope_buf_long[code]), 6))

                # peak_vol_bias
                if code not in peak_vol_state:
                    peak_vol_state[code] = {'max_amount': 0, 'price_at_max': price}
                pv = peak_vol_state[code]
                if amount > pv['max_amount']:
                    pv['max_amount'] = amount
                    pv['price_at_max'] = price
                bias = (price - pv['price_at_max']) / pv['price_at_max'] * 100 if pv['price_at_max'] > 0 else 0
                biases.append(round(bias, 4))

                # high_distance
                if code not in high_state:
                    high_state[code] = {'max_cpct': cpct}
                hs = high_state[code]
                if cpct > hs['max_cpct']:
                    hs['max_cpct'] = cpct
                high_dists.append(round(cpct - hs['max_cpct'], 4))

            df['slope_short'] = slopes_s
            df['slope_long'] = slopes_l
            df['peak_vol_bias'] = biases
            df['high_distance'] = high_dists

            # ---- 批量UPDATE ----
            with engine.connect() as conn:
                for _, row in df.iterrows():
                    sql = text(f"""
                        UPDATE {table}
                        SET min1_change_pct = :m1c, min1_amount = :m1a,
                            amount_rank = :ar,
                            slope_short = :ss, slope_long = :sl,
                            peak_vol_bias = :pvb, high_distance = :hd
                        WHERE bond_code = :code AND time = :t
                    """)
                    conn.execute(sql, {
                        'm1c': float(row['min1_change_pct']),
                        'm1a': float(row['min1_amount']),
                        'ar': int(row['amount_rank']),
                        'ss': float(row['slope_short']),
                        'sl': float(row['slope_long']),
                        'pvb': float(row['peak_vol_bias']),
                        'hd': float(row['high_distance']),
                        'code': row['bond_code'],
                        't': time_str,
                    })
                conn.commit()
                updated_rows += len(df)

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  [ERROR] time={time_str}: {e}")
            continue

        # 进度输出
        if (idx + 1) % 50 == 0 or (idx + 1) == total_tp:
            elapsed = time_mod.time() - start_time
            speed = (idx + 1) / elapsed if elapsed > 0 else 0
            eta = (total_tp - idx - 1) / speed if speed > 0 else 0
            pct = (idx + 1) / total_tp * 100
            print(f"  [{date_str}] {idx+1}/{total_tp} ({pct:.1f}%) | "
                  f"{updated_rows:,} 行 | {speed:.1f} tp/s | "
                  f"耗时 {elapsed:.0f}s | ETA {eta:.0f}s | 失败 {errors}")

    elapsed = time_mod.time() - start_time
    print(f"\n  ✅ [{date_str}] 完成! "
          f"{total_tp} 时间点 | {updated_rows:,} 行 | "
          f"失败 {errors} | 总耗时 {elapsed:.1f}s")
    return True


if __name__ == '__main__':
    dates = sys.argv[1:] if len(sys.argv) > 1 else ['20260706', '20260707', '20260708']

    print(f"{'='*70}")
    print(f"统一回填: min1 + amount_rank + slope + peak_vol_bias + high_distance")
    print(f"目标日期: {', '.join(dates)}")
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
