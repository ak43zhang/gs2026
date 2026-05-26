"""
通过buy-points API获取真正的买点候选数据
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache

data_service = DataService()
cache = get_cache()

date = '20260519'
times = ['09:30:21', '09:31:51', '09:35:00', '09:40:00', '10:00:00']

for t in times:
    print(f"\n=== {t} ===")
    
    # 获取股票数据
    stocks = data_service.get_ranking_at_time(asset_type='stock', limit=500, date=date, time_str=t)
    if not stocks:
        print("  No stock data")
        continue
    
    # 获取行业排行
    industry_data = data_service.get_ranking_at_time(asset_type='industry', limit=10, date=date, time_str=t)
    top_industries = set()
    if industry_data:
        for ind in industry_data:
            name = ind.get('name', '') or ind.get('industry_name', '')
            if name:
                top_industries.add(name)
    
    print(f"  Stocks: {len(stocks)}, Top industries: {len(top_industries)}")
    
    # 补充债券信息
    stock_codes = [s.get('code', '') for s in stocks if s.get('code')]
    mappings = cache.get_mappings_smart(stock_codes)
    
    for stock in stocks:
        code = stock.get('code', '')
        mapping = mappings.get(code)
        if mapping:
            stock['bond_code'] = mapping.get('bond_code', '-')
            stock['industry_name'] = mapping.get('industry_name', '-')
        else:
            stock['bond_code'] = '-'
            stock['industry_name'] = '-'
    
    # 评估条件
    candidates = []
    for stock in stocks:
        cum_net = float(stock.get('cumulative_main_net', 0) or 0)
        peak_net = float(stock.get('max_cumulative_main_net', 0) or 0)
        chg_pct = stock.get('change_pct')
        if isinstance(chg_pct, str):
            try:
                chg_pct = float(chg_pct)
            except:
                chg_pct = None
        
        ratio = cum_net / peak_net if peak_net > 0 else 0
        cond_ratio = ratio > 0.9
        
        ind_name = stock.get('industry_name', '') or ''
        cond_ind = ind_name in top_industries
        
        cond_pct = chg_pct is not None and chg_pct > 0
        
        score = sum([cond_ratio, cond_ind, cond_pct])
        if score >= 2:  # 只取2星和3星
            bond_code = stock.get('bond_code', '-')
            has_bond = bond_code and bond_code != '-'
            candidates.append({
                'code': stock.get('code', ''),
                'name': stock.get('name', ''),
                'price': stock.get('price'),
                'change_pct': chg_pct,
                'bond_code': bond_code if has_bond else '',
                'industry_name': ind_name,
                'cum_net': cum_net,
                'peak_net': peak_net,
                'ratio': ratio,
                'cond_ratio': cond_ratio,
                'cond_ind': cond_ind,
                'cond_pct': cond_pct,
                'score': score,
                'has_bond': has_bond
            })
    
    candidates.sort(key=lambda x: (-x['score'], -x['ratio']))
    
    # 只显示有债券的
    bond_candidates = [c for c in candidates if c['has_bond']]
    
    print(f"  Total candidates (>=2star): {len(candidates)}")
    print(f"  With bond: {len(bond_candidates)}")
    
    for c in bond_candidates[:5]:
        stars = '*' * c['score']
        print(f"    {c['code']} {c['name']} price={c['price']} chg={c['change_pct']}% bond={c['bond_code']} ratio={c['ratio']:.3f} {stars}")
    
    if not bond_candidates and candidates:
        print("  (no bond candidates, showing top without bond)")
        for c in candidates[:3]:
            stars = '*' * c['score']
            print(f"    {c['code']} {c['name']} chg={c['change_pct']}% ind={c['industry_name']} ratio={c['ratio']:.3f} {stars}")
