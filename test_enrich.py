"""Test _enrich_change_pct_and_main_net function directly"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.dashboard2.routes.monitor import _enrich_change_pct_and_main_net

# Test data
test_stocks = [
    {'code': '000539', 'name': '粤电力A', 'count': 10},
    {'code': '002217', 'name': '合力泰', 'count': 8},
]

# Test with specific time
result = _enrich_change_pct_and_main_net(test_stocks, '20260428', '15:00:00')

print("Result:")
for item in result:
    print(f"  Code: {item['code']}")
    print(f"  Name: {item['name']}")
    print(f"  Count: {item['count']}")
    print(f"  Change_pct: {item.get('change_pct', 'NOT_SET')}")
    print(f"  Main_net_amount: {item.get('main_net_amount', 'NOT_SET')}")
    print()
