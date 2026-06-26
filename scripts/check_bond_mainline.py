import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import json

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 1. 获取今天所有非独立个股的 done 股票
    result = conn.execute(text(
        "SELECT stock_code, stock_name, mainline_names "
        "FROM stock_anomaly "
        "WHERE trading_date = '2026-06-25' AND ai_status = 'done' "
        "AND mainline_names IS NOT NULL AND mainline_names != '[\"独立个股\"]'"
    ))
    stocks = result.fetchall()
    
    # 2. 获取所有可交易可转债的正股代码
    result2 = conn.execute(text(
        "SELECT `代码`,`名称`,`现价`,`正股代码`,`正股名称`,`转股价`,`正股价`,`剩余规模`,`强赎状态` "
        "FROM data_bond_qs_jsl "
        "WHERE `现价` IS NOT NULL AND `现价` > 0"
    ))
    bonds = result2.fetchall()
    
    # 3. 建立正股代码 → 可转债映射
    bond_map = {}
    for b in bonds:
        stock_code = b[3]  # 正股代码
        if stock_code:
            if stock_code not in bond_map:
                bond_map[stock_code] = []
            bond_map[stock_code].append({
                'bond_code': b[0], 'bond_name': b[1], 'price': b[2],
                'stock_name': b[4], 'convert_price': b[5], 'stock_price': b[6],
                'remaining': b[7], 'redeem_status': b[8]
            })
    
    print(f"今天非独立个股 done 股票: {len(stocks)} 只")
    print(f"可转债总数: {len(bonds)} 只")
    print(f"有可转债的正股数: {len(bond_map)} 只")
    
    # 4. 匹配
    matches = []
    for s in stocks:
        code, name, ml_raw = s
        ml_list = json.loads(ml_raw) if isinstance(ml_raw, str) else ml_raw
        ml_list = [m for m in ml_list if m != '独立个股']
        
        if code in bond_map:
            for bond in bond_map[code]:
                matches.append({
                    'stock_code': code,
                    'stock_name': name,
                    'mainlines': ml_list,
                    'mainline_count': len(ml_list),
                    'bond_code': bond['bond_code'],
                    'bond_name': bond['bond_name'],
                    'bond_price': bond['price'],
                    'convert_price': bond['convert_price'],
                    'stock_price': bond['stock_price'],
                    'remaining': bond['remaining'],
                    'redeem_status': bond['redeem_status']
                })
    
    # 按主线数降序排序
    matches.sort(key=lambda x: -x['mainline_count'])
    
    print(f"\n=== 匹配到的主线可转债: {len(matches)} 只 ===")
    for m in matches:
        premium = (m['bond_price'] / (m['stock_price'] / m['convert_price'] * 100) - 1) * 100 if m['stock_price'] and m['convert_price'] else 0
        print(f"  {m['bond_name']:8s} ({m['bond_code']}) | 现价:{m['bond_price']:7.2f} | "
              f"正股:{m['stock_name']:6s} | 主线数:{m['mainline_count']} | "
              f"溢价率:{premium:+.1f}% | 剩余:{m['remaining']}亿 | 强赎:{m['redeem_status']}")
        for ml in m['mainlines']:
            print(f"    └─ {ml}")
