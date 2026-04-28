"""Test complete _get_change_pct_and_main_net_batch"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.dashboard2.routes.monitor import _get_change_pct_and_main_net_batch

date = '20260428'
time_str = '15:00:00'
stock_codes = ['000539', '002217']

change_pct_map, main_net_map = _get_change_pct_and_main_net_batch(date, time_str, stock_codes)

print("Change_pct_map:")
for k, v in change_pct_map.items():
    print(f"  {k}: {v}")

print("\nMain_net_map:")
for k, v in main_net_map.items():
    print(f"  {k}: {v}")
