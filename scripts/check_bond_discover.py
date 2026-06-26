"""验证主线→行业→同行业未涨停股票→可转债的完整链路"""
import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import json

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 1. 获取今天主线中龙头/跟风股的行业
    mainline_stocks = conn.execute(text(
        "SELECT stock_code, stock_name, mainline_names "
        "FROM stock_anomaly "
        "WHERE trading_date = '2026-06-25' AND ai_status = 'done' "
        "AND mainline_names IS NOT NULL AND mainline_names != '[\"独立个股\"]'"
    )).fetchall()
    
    # 收集所有主线股票代码
    today_zt_codes = set()
    stock_mainline_map = {}  # stock_code → [mainline_names]
    for s in mainline_stocks:
        code = s[0]
        today_zt_codes.add(code)
        ml_list = json.loads(s[2]) if isinstance(s[2], str) else s[2]
        ml_list = [m for m in ml_list if m != '独立个股']
        stock_mainline_map[code] = ml_list
    
    print(f"今天主线涨停股: {len(today_zt_codes)} 只")
    
    # 2. 获取这些股票的行业（从 data_industry_code_component_ths）
    placeholders = ','.join([f"'{c}'" for c in today_zt_codes])
    industry_result = conn.execute(text(
        f"SELECT stock_code, code as industry_code, name as industry_name "
        f"FROM data_industry_code_component_ths "
        f"WHERE stock_code IN ({placeholders})"
    )).fetchall()
    
    # 建立 主线→行业 映射
    mainline_industries = {}  # mainline_name → set(industry_codes)
    stock_industry = {}  # stock_code → industry_code
    for row in industry_result:
        stock_code, ind_code, ind_name = row
        stock_industry[stock_code] = (ind_code, ind_name)
        # 该股票属于哪些主线 → 这些主线关联这个行业
        if stock_code in stock_mainline_map:
            for ml in stock_mainline_map[stock_code]:
                if ml not in mainline_industries:
                    mainline_industries[ml] = set()
                mainline_industries[ml].add((ind_code, ind_name))
    
    print(f"\n=== 主线→行业映射 ===")
    for ml, industries in sorted(mainline_industries.items(), key=lambda x: -len(x[1])):
        ind_names = [f"{name}({code})" for code, name in industries]
        print(f"  {ml}: {', '.join(ind_names)}")
    
    # 3. 获取这些行业中所有股票
    all_industry_codes = set()
    for inds in mainline_industries.values():
        for code, name in inds:
            all_industry_codes.add(code)
    
    ind_placeholders = ','.join([f"'{c}'" for c in all_industry_codes])
    all_industry_stocks = conn.execute(text(
        f"SELECT stock_code, short_name, code as industry_code, name as industry_name "
        f"FROM data_industry_code_component_ths "
        f"WHERE code IN ({ind_placeholders})"
    )).fetchall()
    
    print(f"\n涉及行业数: {len(all_industry_codes)}")
    print(f"这些行业的全部股票: {len(all_industry_stocks)} 只")
    
    # 4. 排除今天已涨停的
    # 获取所有涨停股票（不限于主线）
    all_zt = conn.execute(text(
        "SELECT stock_code FROM stock_anomaly WHERE trading_date = '2026-06-25'"
    )).fetchall()
    all_zt_codes = set(r[0] for r in all_zt)
    
    candidate_stocks = {}  # stock_code → {name, industries, mainlines}
    for row in all_industry_stocks:
        code, name, ind_code, ind_name = row
        if code in all_zt_codes:
            continue  # 排除今天涨停的
        if code not in candidate_stocks:
            candidate_stocks[code] = {'name': name, 'industries': set(), 'mainlines': set()}
        candidate_stocks[code]['industries'].add((ind_code, ind_name))
        # 通过行业反查属于哪些主线
        for ml, inds in mainline_industries.items():
            if (ind_code, ind_name) in inds:
                candidate_stocks[code]['mainlines'].add(ml)
    
    print(f"排除涨停后候选股票: {len(candidate_stocks)} 只")
    
    # 5. 匹配可转债
    bonds = conn.execute(text(
        "SELECT `代码`,`名称`,`现价`,`正股代码`,`正股名称`,`转股价`,`正股价`,`剩余规模`,`强赎状态` "
        "FROM data_bond_qs_jsl "
        "WHERE `现价` IS NOT NULL AND `现价` > 0 AND `强赎状态` NOT LIKE '%已公告强赎%'"
    )).fetchall()
    
    bond_map = {}
    for b in bonds:
        if b[3]:  # 正股代码
            bond_map[b[3]] = {'bond_code': b[0], 'bond_name': b[1], 'price': b[2],
                             'stock_name': b[4], 'convert_price': b[5], 'stock_price': b[6],
                             'remaining': b[7], 'redeem_status': b[8]}
    
    # 6. 匹配
    results = []
    for code, info in candidate_stocks.items():
        if code in bond_map:
            bond = bond_map[code]
            premium = (bond['price'] / (bond['stock_price'] / bond['convert_price'] * 100) - 1) * 100 if bond['stock_price'] and bond['convert_price'] else 0
            results.append({
                'stock_code': code,
                'stock_name': info['name'],
                'mainline_count': len(info['mainlines']),
                'mainlines': list(info['mainlines']),
                'bond_code': bond['bond_code'],
                'bond_name': bond['bond_name'],
                'bond_price': bond['price'],
                'premium': premium,
                'remaining': bond['remaining'],
                'redeem_status': bond['redeem_status']
            })
    
    # 排序：主线数降序 → 溢价率升序
    results.sort(key=lambda x: (-x['mainline_count'], x['premium']))
    
    print(f"\n=== 挖掘结果: {len(results)} 只主线可转债 ===")
    for r in results[:15]:
        print(f"  {r['bond_name']:8s} ({r['bond_code']}) | 正股:{r['stock_name']:6s} | "
              f"主线数:{r['mainline_count']} | 溢价率:{r['premium']:+.1f}% | 剩余:{r['remaining']}亿")
        for ml in r['mainlines'][:3]:
            print(f"    └─ {ml}")
        if len(r['mainlines']) > 3:
            print(f"    └─ ...共{len(r['mainlines'])}条")
