import sys
sys.path.insert(0, 'src')

# 模拟调用 _enrich_bond_data
from gs2026.dashboard2.routes.monitor import _enrich_bond_data

# 测试数据
bonds = [
    {'code': '123054', 'name': '思特转债', 'count': 156},
    {'code': '113601', 'name': 'Z泰1转', 'count': 141},
]

date = '20260403'

# 测试实时场景（time_str=None）
print("=== 测试实时场景 ===")
result = _enrich_bond_data(bonds, date, None)
for bond in result:
    print(f"代码: {bond['code']}, 涨跌幅: {bond['change_pct']}")
