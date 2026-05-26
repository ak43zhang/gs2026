"""
对比14:20:00和14:20:03的605358数据差异
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache

data_service = DataService()
cache = get_cache()
db_engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

date = '20260519'
table = f'monitor_gp_sssj_{date}'
bond_table = f'monitor_zq_sssj_{date}'

# 1. 检查605358在两个时间点的股票数据
print("=== 1. 股票数据对比 ===")
for t in ['14:20:00', '14:20:03', '14:20:21']:
    with db_engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT stock_code, short_name, price, change_pct, cumulative_main_net, 
                   max_cumulative_main_net, consecutive_attacks
            FROM {table}
            WHERE time = '{t}' AND stock_code = '605358'
        """))
        row = result.fetchone()
        if row:
            ratio = float(row[4]) / float(row[5]) if float(row[5]) > 0 else 0
            print(f"  {t}: code={row[0]} name={row[1]} price={row[2]} chg={row[3]}% cum={row[4]} peak={row[5]} consec={row[6]} ratio={ratio:.3f}")
        else:
            print(f"  {t}: no data for 605358")

# 2. 检查605358的债券映射
print("\n=== 2. 债券映射 ===")
mappings = cache.get_mappings_smart(['605358'])
mapping = mappings.get('605358', {})
bond_code = mapping.get('bond_code', '-') if mapping else '-'
print(f"  605358 -> bond_code={bond_code}")
print(f"  full mapping: {mapping}")

# 3. 检查债券排行中是否有该债券
print("\n=== 3. 债券排行对比 ===")
for t in ['14:20:00', '14:20:03', '14:20:21']:
    bond_rank = data_service.get_ranking_at_time(asset_type='bond', limit=30, date=date, time_str=t)
    bond_rank_set = set()
    bond_rank_map = {}
    if bond_rank:
        for b in bond_rank:
            bc = str(b.get('code', ''))
            bond_rank_set.add(bc)
            bond_rank_map[bc] = b
    
    in_rank = bond_code in bond_rank_set
    bond_data = bond_rank_map.get(bond_code, {})
    bond_chg = bond_data.get('change_pct', 'N/A')
    print(f"  {t}: bond {bond_code} in_rank={in_rank} bond_chg={bond_chg}")

# 4. 检查行业排行
print("\n=== 4. 行业排行对比 ===")
ind_name = mapping.get('industry_name', '-') if mapping else '-'
print(f"  605358 industry: {ind_name}")
for t in ['14:20:00', '14:20:03', '14:20:21']:
    industry_data = data_service.get_ranking_at_time(asset_type='industry', limit=10, date=date, time_str=t)
    top_industries = set()
    if industry_data:
        for ind in industry_data:
            name = ind.get('name', '') or ind.get('industry_name', '')
            if name:
                top_industries.add(name)
    in_top = ind_name in top_industries
    print(f"  {t}: ind={ind_name} in_top10={in_top} industries={top_industries}")

# 5. 检查填充脚本入库的数据
print("\n=== 5. 已入库数据 ===")
with db_engine.connect() as conn:
    result = conn.execute(text("""
        SELECT time, stock_code, stock_name, stock_change_pct, bond_code, bond_change_pct, level, conditions
        FROM buy_point_candidates 
        WHERE date = '2026-05-19' AND stock_code = '605358'
    """))
    for row in result:
        print(f"  time={row[0]} code={row[1]} name={row[2]} chg={row[3]}% bond={row[4]} bond_chg={row[5]} lv={row[6]}")
        print(f"    conditions={row[7]}")

# 6. 检查可用时间点
print("\n=== 6. 14:20附近的可用时间点 ===")
with db_engine.connect() as conn:
    result = conn.execute(text(f"""
        SELECT DISTINCT time FROM {table} 
        WHERE time BETWEEN '14:19:50' AND '14:20:10' 
        ORDER BY time
    """))
    for row in result:
        print(f"  {row[0]}")
