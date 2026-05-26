"""
单独验证14:20:03的605358是否能正确计算为3星
"""
import sys, json, hashlib
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache

data_service = DataService()
cache = get_cache()
db_engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

date = '20260519'
time_str = '14:20:03'
table = f'monitor_gp_sssj_{date}'
bond_table = f'monitor_zq_sssj_{date}'

print(f"=== Verify 605358 at {time_str} ===\n")

# 1. 获取股票数据
with db_engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT stock_code, short_name, price, change_pct, cumulative_main_net, 
               max_cumulative_main_net, consecutive_attacks
        FROM {table} WHERE time = '{time_str}' AND stock_code = '605358'
    """))
    row = result.fetchone()
    chg = float(row[3])
    cum = float(row[4])
    peak = float(row[5])
    consec = int(row[6])
    ratio = cum / peak if peak > 0 else 0
    price = float(row[2])
    print(f"Stock: 605358 price={price} chg={chg}% cum={cum} peak={peak} consec={consec} ratio={ratio:.3f}")

# 2. 债券映射
mappings = cache.get_mappings_smart(['605358'])
mapping = mappings.get('605358', {})
bond_code = mapping.get('bond_code', '-')
ind_name = mapping.get('industry_name', '-')
print(f"Bond: {bond_code}, Industry: {ind_name}")

# 3. 债券排行
bond_rank = data_service.get_ranking_at_time(asset_type='bond', limit=30, date=date, time_str=time_str)
bond_rank_set = set()
bond_rank_map = {}
if bond_rank:
    for b in bond_rank:
        bc = str(b.get('code', ''))
        bond_rank_set.add(bc)
        bond_rank_map[bc] = b

in_rank = bond_code in bond_rank_set
print(f"Bond in rank: {in_rank}")

# 4. 【关键修复】从monitor_zq_sssj获取债券真实涨幅
bond_chg_val = 0
bond_price_val = None
if bond_rank_set:
    bond_codes_str = ','.join([f"'{c}'" for c in bond_rank_set])
    with db_engine.connect() as conn:
        bond_df = pd.read_sql(text(f"""
            SELECT bond_code, change_pct, price
            FROM {bond_table}
            WHERE time = '{time_str}' AND bond_code IN ({bond_codes_str})
        """), conn)
        
        if not bond_df.empty:
            bond_df['bond_code'] = bond_df['bond_code'].astype(str)
            for _, brow in bond_df.iterrows():
                bc = brow['bond_code']
                if bc in bond_rank_map:
                    bond_rank_map[bc]['change_pct'] = float(brow['change_pct'])
                    bond_rank_map[bc]['price'] = float(brow['price'])

bond_data = bond_rank_map.get(bond_code, {})
bond_chg_val = float(bond_data.get('change_pct', 0) or 0)
bond_price_val = bond_data.get('price')
print(f"Bond {bond_code}: chg={bond_chg_val}%, price={bond_price_val}")

# 5. 行业排行
industry_data = data_service.get_ranking_at_time(asset_type='industry', limit=10, date=date, time_str=time_str)
top_industries = set()
if industry_data:
    for ind in industry_data:
        name = ind.get('name', '') or ind.get('industry_name', '')
        if name:
            top_industries.add(name)
cond_ind = ind_name in top_industries
print(f"Industry {ind_name} in top10: {cond_ind}")

# 6. 评估条件
print(f"\n=== Conditions ===")
cond_ratio = ratio > 0.9
cond_chg = chg > 2
cond_consec = consec > 0
cond_bond_rank = in_rank
cond_bond_chg = bond_chg_val > 2

print(f"  [Required] ratio>0.9: {cond_ratio} ({ratio:.3f})")
print(f"  [Required] chg>2%: {cond_chg} ({chg}%)")
print(f"  [Required] consec>0: {cond_consec} ({consec})")
print(f"  [Required] bond_in_rank: {cond_bond_rank}")
print(f"  [Bonus] ind_top10: {cond_ind}")
print(f"  [Bonus] bond_chg>2%: {cond_bond_chg} ({bond_chg_val}%)")

required_pass = cond_ratio and cond_chg and cond_consec and cond_bond_rank
bonus = sum([cond_ind, cond_bond_chg])
level = 1 + min(bonus, 2)

print(f"\n  Required all pass: {required_pass}")
print(f"  Bonus count: {bonus}")
print(f"  Level: {level} star{'s' if level > 1 else ''}")

if required_pass and level >= 2:
    print(f"\n=== RESULT: 605358 at {time_str} = {level} STARS ===")
else:
    print(f"\n=== RESULT: NOT QUALIFIED ===")
