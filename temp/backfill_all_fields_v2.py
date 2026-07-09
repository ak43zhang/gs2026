"""
统一回填脚本V2：支持扩展指标（weighted_slope_2m, change_1m_pct, price_acceleration）

新增字段:
  - weighted_slope_2m: 2分钟加权斜率
  - change_1m_pct: 1分钟变化率%
  - price_acceleration: 价格加速度
  - ext_indicators: JSON扩展字段（包含以上指标）

与实时计算逻辑一致: 使用 bond_indicators.py 的批量计算函数

用法:
  python backfill_all_fields_v2.py [dates...]
  python backfill_all_fields_v2.py 20260709
"""
import sys
import time as time_mod
from collections import deque

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.dashboard2.config import Config

# 导入精确计算函数
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\services')
from bond_indicators import (
    calc_weighted_slope_batch,
    calc_change_rate_batch,
    calc_acceleration_batch
)

engine = create_engine(
    Config.MYSQL_URI,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=0,
)

# ====== 常量 ======
COMMIT_BATCH = 20  # 每20个时间点提交一次

# 原有字段（保持不变）
ORIGINAL_COLUMNS = [
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

# 新增扩展指标字段
EXT_INDICATOR_COLUMNS = [
    ('weighted_slope_2m', 'DECIMAL(10,6) DEFAULT NULL'),
    ('change_1m_pct', 'DECIMAL(6,4) DEFAULT NULL'),
    ('price_acceleration', 'DECIMAL(10,6) DEFAULT NULL'),
]

# 扩展JSON字段
EXT_JSON_COLUMN = ('ext_indicators', 'JSON NULL')

# 所有字段
ALL_COLUMNS = ORIGINAL_COLUMNS + EXT_INDICATOR_COLUMNS + [EXT_JSON_COLUMN]


def calc_slope(buf):
    """线性回归斜率 - 原有计算"""
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


def calc_weighted_slope_for_backfill(prices, times, window=120, half_life=30):
    """
    为回填计算加权斜率
    
    参数:
        prices: 价格列表
        times: 时间列表（秒）
        window: 窗口秒数
        half_life: 半衰期秒数
    """
    return calc_weighted_slope_batch(prices, times, window, half_life)


def backfill_table(date_str):
    table = f"monitor_zq_sssj_{date_str}"
    print(f"\n{'='*70}")
    print(f"[{date_str}] 统一回填V2: {table}")
    print(f"  新增字段: weighted_slope_2m, change_1m_pct, price_acceleration")
    print(f"{'='*70}")

    conn = engine.raw_connection()
    cursor = conn.cursor()

    try:
        # 1. 检查表是否存在
        cursor.execute(f"SHOW TABLES LIKE '{table}'")
        if not cursor.fetchone():
            print(f"  ⚠️ 表不存在，跳过")
            return False

        # 2. 添加缺失列（包括原有和新增）
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        existing_cols = {row[0] for row in cursor.fetchall()}
        added = []
        for col_name, col_def in ALL_COLUMNS:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN `{col_name}` {col_def}")
                    added.append(col_name)
                except Exception as e:
                    print(f"  添加列 {col_name} 失败: {e}")
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

        # 4. 初始化增量状态（原有字段）
        min1_base_minute = None
        min1_base_pct = {}
        min1_base_amt = {}
        slope_buf_short = {}
        slope_buf_long = {}
        peak_vol_state = {}
        high_state = {}
        mkt_slope_buf_short = deque(maxlen=60)
        mkt_slope_buf_long = deque(maxlen=300)
        mkt_peak_vol = {'max_total_amt': 0, 'pct_at_max': 0.0}
        mkt_high = {'max_avg_pct': -999.0}
        
        # 新增：扩展指标缓存
        ext_price_cache = {}  # bond_code -> [(timestamp, price), ...]
        ext_slope_cache = {}  # bond_code -> last slope

        # 准备UPDATE SQL（包含新增字段）
        update_sql = f"""
            UPDATE {table}
            SET min1_change_pct=%s, min1_amount=%s, amount_rank=%s,
                slope_short=%s, slope_long=%s, peak_vol_bias=%s, high_distance=%s,
                mkt_slope_short=%s, mkt_slope_long=%s, mkt_peak_vol_bias=%s, mkt_high_distance=%s,
                weighted_slope_2m=%s, change_1m_pct=%s, price_acceleration=%s,
                ext_indicators=%s
            WHERE bond_code=%s AND time=%s
        """

        start_time = time_mod.time()
        updated_rows = 0
        errors = 0
        batch_params = []

        # 5. 逐时间点处理
        for idx, t in enumerate(times):
            time_str = str(t).zfill(6)
            current_minute = time_str[:4]  # HHMM
            
            # 将HHMMSS转换为秒（从当天00:00:00开始）
            try:
                hh = int(time_str[:2])
                mm = int(time_str[2:4])
                ss = int(time_str[4:6])
                current_seconds = hh * 3600 + mm * 60 + ss
            except:
                current_seconds = idx * 3  # 假设3秒间隔

            try:
                # 加载该时间点数据
                cursor.execute(
                    f"SELECT bond_code, change_pct, price, amount FROM {table} WHERE time = %s",
                    (t,)
                )
                rows = cursor.fetchall()
                if not rows:
                    continue

                codes = [r[0] for r in rows]
                cpcts = [r[1] for r in rows]
                prices = [r[2] for r in rows]
                amounts = [r[3] for r in rows]

                # ========== 原有字段计算 ==========
                # 分钟切换检测
                if current_minute != min1_base_minute:
                    min1_base_minute = current_minute
                    min1_base_pct = {c: p for c, p in zip(codes, cpcts)}
                    min1_base_amt = {c: a for c, a in zip(codes, amounts)}

                # 金额排名
                sorted_amts = sorted(amounts, reverse=True)
                amount_ranks = [sorted_amts.index(a) + 1 for a in amounts]

                # 大盘指标
                mkt_avg_pct = sum(cpcts) / len(cpcts) if cpcts else 0
                mkt_slope_buf_short.append(mkt_avg_pct)
                mkt_slope_buf_long.append(mkt_avg_pct)
                mkt_ss = round(calc_slope(mkt_slope_buf_short), 6)
                mkt_sl = round(calc_slope(mkt_slope_buf_long), 6)

                total_amt = sum(amounts)
                if total_amt > mkt_peak_vol['max_total_amt']:
                    mkt_peak_vol['max_total_amt'] = total_amt
                    mkt_peak_vol['pct_at_max'] = mkt_avg_pct
                mkt_pvb = round(mkt_avg_pct - mkt_peak_vol['pct_at_max'], 4)

                if mkt_avg_pct > mkt_high['max_avg_pct']:
                    mkt_high['max_avg_pct'] = mkt_avg_pct
                mkt_hd = round(mkt_avg_pct - mkt_high['max_avg_pct'], 4)

                # ========== 逐个债券计算（原有+新增） ==========
                for i, code in enumerate(codes):
                    cpct = cpcts[i]
                    price = prices[i]
                    amount = amounts[i]

                    # 原有字段
                    m1c = round(cpct - min1_base_pct.get(code, cpct), 4)
                    m1a = round(amount - min1_base_amt.get(code, amount), 0)

                    if code not in slope_buf_short:
                        slope_buf_short[code] = deque(maxlen=60)
                    slope_buf_short[code].append(cpct)
                    ss = round(calc_slope(slope_buf_short[code]), 6)

                    if code not in slope_buf_long:
                        slope_buf_long[code] = deque(maxlen=300)
                    slope_long[code].append(cpct)
                    sl = round(calc_slope(slope_buf_long[code]), 6)

                    if code not in peak_vol_state:
                        peak_vol_state[code] = {'max_amount': 0, 'price_at_max': price}
                    pv = peak_vol_state[code]
                    if amount > pv['max_amount']:
                        pv['max_amount'] = amount
                        pv['price_at_max'] = price
                    pvb = round((price - pv['price_at_max']) / pv['price_at_max'] * 100, 4) if pv['price_at_max'] > 0 else 0

                    if code not in high_state:
                        high_state[code] = {'max_cpct': cpct}
                    hs = high_state[code]
                    if cpct > hs['max_cpct']:
                        hs['max_cpct'] = cpct
                    hd = round(cpct - hs['max_cpct'], 4)

                    # ========== 新增扩展指标计算 ==========
                    # 更新价格缓存
                    if code not in ext_price_cache:
                        ext_price_cache[code] = []
                    ext_price_cache[code].append((current_seconds, price))
                    # 保留2分钟+30秒的数据（用于计算）
                    cutoff = current_seconds - 150
                    ext_price_cache[code] = [
                        (ts, p) for ts, p in ext_price_cache[code] if ts >= cutoff
                    ]
                    
                    # 计算加权斜率
                    cache = ext_price_cache[code]
                    if len(cache) >= 2:
                        cache_prices = [p for _, p in cache]
                        cache_times = [t for t, _ in cache]
                        ws = calc_weighted_slope_for_backfill(
                            cache_prices, cache_times, window=120, half_life=30
                        )
                    else:
                        ws = 0.0
                    
                    # 计算1分钟变化率
                    if len(cache) >= 2:
                        # 找60秒前的价格
                        target_ts = current_seconds - 60
                        price_1m_ago = None
                        for ts, p in reversed(cache):
                            if ts <= target_ts:
                                price_1m_ago = p
                                break
                        if price_1m_ago is not None and price_1m_ago != 0:
                            c1p = calc_change_rate_batch(price, price_1m_ago)
                        else:
                            c1p = 0.0
                    else:
                        c1p = 0.0
                    
                    # 计算加速度（需要上一周期的斜率）
                    prev_slope = ext_slope_cache.get(code, 0.0)
                    pa = calc_acceleration_batch(ws, prev_slope)
                    ext_slope_cache[code] = ws  # 保存当前斜率用于下次
                    
                    # 构建ext_indicators JSON
                    ext_json = {
                        'weighted_slope_2m': round(ws, 6),
                        'change_1m_pct': round(c1p, 4),
                        'price_acceleration': round(pa, 6),
                    }
                    ext_json_str = json.dumps(ext_json, ensure_ascii=False)
                    
                    # 累积参数（包含新增字段）
                    batch_params.append((
                        m1c, m1a, amount_ranks[i], ss, sl, pvb, hd,  # 原有7个
                        mkt_ss, mkt_sl, mkt_pvb, mkt_hd,  # 大盘4个
                        round(ws, 6), round(c1p, 4), round(pa, 6),  # 新增3个
                        ext_json_str,  # JSON
                        code, time_str  # WHERE条件
                    ))

                updated_rows += len(codes)

            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  [ERROR] time={time_str}: {e}")
                    import traceback
                    traceback.print_exc()
                continue

            # 批量提交
            if (idx + 1) % COMMIT_BATCH == 0 or (idx + 1) == total_tp:
                if batch_params:
                    try:
                        cursor.executemany(update_sql, batch_params)
                        conn.commit()
                    except Exception as e:
                        print(f"  [ERROR] 批量提交失败: {e}")
                        conn.rollback()
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
            try:
                cursor.executemany(update_sql, batch_params)
                conn.commit()
            except Exception as e:
                print(f"  [ERROR] 最终提交失败: {e}")

        elapsed = time_mod.time() - start_time
        print(f"\n  ✅ [{date_str}] 完成! "
              f"{total_tp} 时间点 | {updated_rows:,} 行 | "
              f"失败 {errors} | 总耗时 {elapsed:.1f}s")
        return True

    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    import json
    
    dates = sys.argv[1:] if len(sys.argv) > 1 else ['20260709']

    print(f"{'='*70}")
    print(f"统一回填V2: 支持扩展指标")
    print(f"目标日期: {', '.join(dates)}")
    print(f"新增字段: weighted_slope_2m, change_1m_pct, price_acceleration, ext_indicators")
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
