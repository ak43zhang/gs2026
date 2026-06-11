"""验证绿名单缓存日期格式"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.routes.green_bond_list_cache import get_green_bond_list_cache_date, get_green_bond_list

cache_date = get_green_bond_list_cache_date()
print(f"Redis缓存日期: {cache_date!r} (type: {type(cache_date)})")

green_list = get_green_bond_list()
print(f"Redis绿名单数量: {len(green_list)}")
print(f"样本: {list(green_list)[:3] if green_list else 'None'}")

# 测试比较
test_dates = ['20260609', '20260610', '20260611']
for d in test_dates:
    is_match = (cache_date == d)
    print(f"cache_date({cache_date}) == '{d}' -> {is_match}")
