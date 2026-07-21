"""性能分段计时测试"""
import time
import sys
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, 'src')
from gs2026.utils import config_util
from gs2026.dashboard2.services.backtest_bond import _build_full_where

engine = config_util.get_engine()

date = '20260720'
table = f'monitor_zq_sssj_{date}'
conditions = [
    {'field': 'change_pct', 'op': '>', 'value': 0.2},
    {'field': 'amount_rank', 'op': '<=', 'value': 50}
]

# === Phase 1: SQL下推获取信号 ===
t1 = time.time()
where_clause, where_params = _build_full_where(conditions, [])
signal_sql = text(f"""
    SELECT bond_code, bond_name, time, price, change_pct, amount
    FROM `{table}`
    WHERE time >= :time_start AND time <= :time_end
    AND {where_clause}
""")
all_params = {'time_start': '09:30:00', 'time_end': '14:50:00'}
all_params.update(where_params)

with engine.connect() as conn:
    df_signals = pd.read_sql(signal_sql, conn, params=all_params)
t2 = time.time()
print(f"Phase 1 (SQL下推): {t2-t1:.2f}s, 信号数: {len(df_signals)}, 债券数: {df_signals['bond_code'].nunique()}")

# === Phase 2: 查询价格序列 ===
signal_codes = df_signals['bond_code'].unique().tolist()
t3 = time.time()
codes_str = ','.join([f"'{c}'" for c in signal_codes[:200]])
price_sql = text(f"""
    SELECT bond_code, time, price
    FROM {table}
    WHERE bond_code IN ({codes_str})
      AND time >= '09:30:00' AND time <= '15:00:00'
    ORDER BY bond_code, time
""")
with engine.connect() as conn:
    df_prices = pd.read_sql(price_sql, conn)
t4 = time.time()
print(f"Phase 2 (价格序列, 前200债): {t4-t3:.2f}s, 行数: {len(df_prices)}")

# === 对比：旧方案加载全表 ===
t5 = time.time()
old_sql = text(f"""
    SELECT bond_code, bond_name, time, price, change_pct, amount,
           amount_rank, min1_change_pct, min1_amount, min1_amount_rank,
           slope_short, slope_long, peak_vol_bias, high_distance,
           mkt_slope_short, mkt_slope_long, mkt_peak_vol_bias, mkt_high_distance,
           ext_indicators
    FROM `{table}`
    WHERE time >= '09:30:00' AND time <= '14:50:00'
""")
with engine.connect() as conn:
    df_old = pd.read_sql(old_sql, conn)
t6 = time.time()
print(f"\n旧方案 Phase1 (加载全表): {t6-t5:.2f}s, 行数: {len(df_old)}")
print(f"\n=== 总结 ===")
print(f"新Phase1: {t2-t1:.2f}s (SQL下推)")
print(f"旧Phase1: {t6-t5:.2f}s (全表加载，还未含JSON展开)")
print(f"Phase 1 提速: {(t6-t5)/(t2-t1):.1f}x")
