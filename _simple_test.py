import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.dashboard2.routes.monitor import _enrich_bond_data

# 测试
data = [{'code': '123118', 'name': '惠城转债', 'count': 80, 'rank': 1}]
result = _enrich_bond_data(data, '20260731', '09:40:03')
print("window_count:", result[0].get('window_count', 'NOT FOUND'))
print("count:", result[0]['count'])
print("keys:", list(result[0].keys()))
