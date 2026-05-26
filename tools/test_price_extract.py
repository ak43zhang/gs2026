import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.routes.monitor import _get_change_pct_and_main_net_batch

# 测试 10:29:06
result = _get_change_pct_and_main_net_batch('20260518', '10:29:06', ['000001', '000002', '000003'])
print(f"Result: {result}")
print(f"derived_maps has price: {'price' in result[2] if len(result) > 2 else 'N/A'}")
if len(result) > 2 and 'price' in result[2]:
    print(f"Sample price: {list(result[2]['price'].items())[:3]}")
