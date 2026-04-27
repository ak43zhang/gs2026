"""排查行业显示bug"""
from gs2026.dashboard2.services import stock_picker_service as sps

# 加载缓存
sps.load_memory_cache()

# 检查几个股票的缓存数据
test_codes = ['000810', '300853', '000001', '000002']

for code in test_codes:
    if code in sps._stock_cache:
        data = sps._stock_cache[code]
        print(f"{code}: industries={list(data['industries'])}, concepts={len(data['concepts'])}")
    else:
        print(f"{code}: NOT IN CACHE")

# 模拟查询 - 用000810所在的行业
code = '000810'
if code in sps._stock_cache:
    data = sps._stock_cache[code]
    print(f"\n{code} detail:")
    print(f"  industries: {data['industries']}")
    print(f"  stock_name: {data['stock_name']}")
