"""
深度诊断：检查stock数据中各条件字段的实际值
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache

data_service = DataService()
cache = get_cache()

date = '20260519'
t = '09:31:51'

stocks = data_service.get_ranking_at_time(asset_type='stock', limit=500, date=date, time_str=t)
industry_data = data_service.get_ranking_at_time(asset_type='industry', limit=10, date=date, time_str=t)

top_industries = set()
if industry_data:
    for ind in industry_data:
        name = ind.get('name', '') or ind.get('industry_name', '')
        if name:
            top_industries.add(name)

print(f"Top industries: {top_industries}")
print(f"Stock count: {len(stocks)}")

# 补充信息
stock_codes = [s.get('code', '') for s in stocks if s.get('code')]
mappings = cache.get_mappings_smart(stock_codes)
for stock in stocks:
    code = stock.get('code', '')
    mapping = mappings.get(code)
    if mapping:
        stock['bond_code'] = mapping.get('bond_code', '-')
        stock['industry_name'] = mapping.get('industry_name', '-')

# 诊断前10个股票的各字段
print("\n=== Top 10 stocks detail ===")
for stock in stocks[:10]:
    code = stock.get('code', '')
    name = stock.get('name', '')
    cum_net = stock.get('cumulative_main_net')
    peak_net = stock.get('max_cumulative_main_net')
    chg_pct = stock.get('change_pct')
    ind_name = stock.get('industry_name', '')
    bond_code = stock.get('bond_code', '-')
    
    # 计算条件
    cum_f = float(cum_net or 0)
    peak_f = float(peak_net or 0)
    ratio = cum_f / peak_f if peak_f > 0 else 0
    cond_ratio = ratio > 0.9
    cond_ind = ind_name in top_industries
    cond_pct = chg_pct is not None and float(chg_pct) > 0 if chg_pct else False
    score = sum([cond_ratio, cond_ind, cond_pct])
    
    print(f"  {code} {name}")
    print(f"    cum_net={cum_net} peak_net={peak_net} ratio={ratio:.3f} cond_ratio={cond_ratio}")
    print(f"    industry={ind_name} cond_ind={cond_ind}")
    print(f"    change_pct={chg_pct} cond_pct={cond_pct}")
    print(f"    bond={bond_code} score={score}")
    print()
