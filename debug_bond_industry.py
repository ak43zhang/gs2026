"""
排查债券行业信息问题
"""
from gs2026.utils.stock_bond_mapping_cache import get_cache
from gs2026.utils import redis_util

# 初始化Redis
redis_util.init_redis()

cache = get_cache()
mappings = cache.get_all_mapping()

print(f"总映射数: {len(mappings)}")

# 查找所有有债券的映射
bonds_with_industry = []
for stock_code, mapping in mappings.items():
    bond_code = mapping.get('bond_code')
    if bond_code:
        # 解码bytes
        if isinstance(stock_code, bytes):
            stock_code = stock_code.decode('utf-8')
        if isinstance(bond_code, bytes):
            bond_code = bond_code.decode('utf-8')
        industry = mapping.get('industry_name', '-')
        if isinstance(industry, bytes):
            industry = industry.decode('utf-8')
        bonds_with_industry.append({
            'stock_code': stock_code,
            'bond_code': bond_code,
            'industry': industry
        })

print(f"\n有债券的映射数: {len(bonds_with_industry)}")
print("\n前10个:")
for b in bonds_with_industry[:10]:
    print(f"  {b['bond_code']} ({b['stock_code']}): {b['industry']}")

# 查找塞力转债
print("\n查找塞力转债...")
for b in bonds_with_industry:
    if '塞力' in b['industry'] or b['bond_code'] == '113801':
        print(f"找到塞力转债: {b}")

# 查找塞力医疗(603716)的正股
print("\n查找603716的映射:")
for stock_code, mapping in mappings.items():
    if isinstance(stock_code, bytes):
        stock_code = stock_code.decode('utf-8')
    if stock_code == '603716':
        print(f"  {stock_code}: {mapping}")
