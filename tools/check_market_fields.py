"""Check market stats data fields"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard.services.data_service import DataService
ds = DataService()
data = ds.get_market_stats(use_mysql=True)
if data:
    for key in ['stock', 'bond']:
        d = data.get(key, {})
        print(f'{key}: {list(d.keys())}')
        print(f'  min_up={d.get("min_up")}, min_down={d.get("min_down")}, min_up_down_ratio={d.get("min_up_down_ratio")}')
        print(f'  cur_up={d.get("cur_up")}, cur_down={d.get("cur_down")}')
        print(f'  body_up={d.get("body_up")}, body_down={d.get("body_down")}')
else:
    print("No data!")
