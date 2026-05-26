import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.routes.monitor import _get_bond_change_pct_batch

# 测试 10:29:06
result = _get_bond_change_pct_batch('20260518', '10:29:06', ['110072', '110073', '110074'])
print(f"Result type: {type(result)}")
print(f"Result: {result}")

# 检查第一个值的类型
if result:
    first_key = list(result.keys())[0]
    first_val = result[first_key]
    print(f"First value type: {type(first_val)}")
    print(f"First value: {first_val}")
