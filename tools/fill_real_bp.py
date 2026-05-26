"""
按照真实买点候选逻辑填充今日数据
条件：
  必要（全部通过）：主力/峰值>0.9, 涨幅>2%, 连续上攻>0, 债券在排行
  加分（决定星级）：行业前10, 债券涨幅>2%
  星级 = 1 + min(bonus, 2)
  只保存 >= 2星
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
save_date = '2026-05-19'
table = f'monitor_gp_sssj_{date}'

# 先清除今天数据
with db_engine.connect() as conn:
    conn.execute(text("DELETE FROM buy_point_candidates WHERE date = '2026-05-19'"))
    conn.commit()
    print("Cleared old data")

# 获取所有可用时间点
with db_engine.connect() as conn:
    result = conn.execute(text(f"SELECT DISTINCT time FROM {table} ORDER BY time"))
    all_times = [str(row[0]) for row in result]
print(f"Available times: {len(all_times)}")

# 采样时间点（使用全量，每3秒都处理）
sample_times = all_times

print(f"Sample times: {len(sample_times)}")

insert_sql = text("""
    INSERT INTO buy_point_candidates 
    (record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,
     bond_code, bond_price, bond_change_pct, level, condition_count, total_conditions,
     conditions, market_context)
    VALUES (:record_id, :date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,
     :bond_code, :bond_price, :bond_change_pct, :level, :condition_count, :total_conditions,
     :conditions, :market_context)
    ON DUPLICATE KEY UPDATE
    stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),
    level=VALUES(level), conditions=VALUES(conditions)
""")

total_inserted = 0

for time_str in sample_times:
    # 1. 获取股票上攻排行
    stocks = data_service.get_ranking_at_time(asset_type='stock', limit=500, date=date, time_str=time_str)
    if not stocks:
        continue
    
    # 2. 补充债券/行业信息
    stock_codes = [s.get('code', '') for s in stocks if s.get('code')]
    if not stock_codes:
        continue
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
    
    # 3. 从sssj表补充涨跌幅/主力净额/连续上攻/价格
    codes_str = ','.join([f"'{c}'" for c in stock_codes])
    try:
        with db_engine.connect() as conn:
            df = pd.read_sql(text(f"""
                SELECT stock_code, change_pct, cumulative_main_net, max_cumulative_main_net, 
                       consecutive_attacks, price
                FROM {table}
                WHERE time = '{time_str}' AND stock_code IN ({codes_str})
            """), conn)
    except:
        continue
    
    if df.empty:
        continue
    
    df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
    chg_map = dict(zip(df['stock_code'], df['change_pct'].astype(float)))
    net_map = dict(zip(df['stock_code'], df['cumulative_main_net'].fillna(0).astype(float)))
    peak_map = dict(zip(df['stock_code'], df['max_cumulative_main_net'].fillna(0).astype(float)))
    consec_map = dict(zip(df['stock_code'], df['consecutive_attacks'].fillna(0).astype(int)))
    price_map = dict(zip(df['stock_code'], df['price'].fillna(0).astype(float)))
    
    for stock in stocks:
        code = stock.get('code', '')
        stock['change_pct'] = chg_map.get(code)
        stock['cumulative_main_net'] = net_map.get(code, 0)
        stock['max_cumulative_main_net'] = peak_map.get(code, 0)
        stock['consecutive_attacks'] = consec_map.get(code, 0)
        stock['price'] = price_map.get(code)
    
    # 4. 获取行业排行前10
    industry_data = data_service.get_ranking_at_time(asset_type='industry', limit=10, date=date, time_str=time_str)
    top_industries = set()
    if industry_data:
        for ind in industry_data:
            name = ind.get('name', '') or ind.get('industry_name', '')
            if name:
                top_industries.add(name)
    
    # 5. 获取债券上攻排行
    bond_rank = data_service.get_ranking_at_time(asset_type='bond', limit=30, date=date, time_str=time_str)
    bond_rank_set = set()
    bond_rank_map = {}
    if bond_rank:
        for b in bond_rank:
            bc = str(b.get('code', ''))
            bond_rank_set.add(bc)
            bond_rank_map[bc] = b
    
    # 5.5 从monitor_zq_sssj获取债券真实涨幅和价格
    if bond_rank_set:
        bond_codes_str = ','.join([f"'{c}'" for c in bond_rank_set])
        try:
            with db_engine.connect() as conn:
                bond_df = pd.read_sql(text(f"""
                    SELECT bond_code, change_pct, price
                    FROM monitor_zq_sssj_{date}
                    WHERE time = '{time_str}' AND bond_code IN ({bond_codes_str})
                """), conn)
                
                if not bond_df.empty:
                    bond_df['bond_code'] = bond_df['bond_code'].astype(str)
                    for _, brow in bond_df.iterrows():
                        bc = brow['bond_code']
                        if bc in bond_rank_map:
                            bond_rank_map[bc]['change_pct'] = float(brow['change_pct'])
                            bond_rank_map[bc]['price'] = float(brow['price'])
        except Exception as e:
            pass  # 查询失败不影响必要条件判断
    
    # 6. 获取大盘数据（用于market_context）
    market_data = data_service.get_market_stats(date=date, use_mysql=True, time_str=time_str)
    stock_stats = market_data.get('stock', {}) if market_data else {}
    bond_stats = market_data.get('bond', {}) if market_data else {}
    if not stock_stats:
        stock_stats = {}
    if not bond_stats:
        bond_stats = {}
    
    body_up = float(stock_stats.get('body_up', 0) or 0)
    cur_up = float(stock_stats.get('cur_up', 0) or 0)
    min_up = float(stock_stats.get('min_up', 0) or 0)
    min_down = float(stock_stats.get('min_down', 0) or 0)
    tick_ratio = round(min_up / min_down, 2) if min_down > 0 else 0
    
    b_body_up = float(bond_stats.get('body_up', 0) or 0)
    b_cur_up = float(bond_stats.get('cur_up', 0) or 0)
    b_min_up = float(bond_stats.get('min_up', 0) or 0)
    b_min_down = float(bond_stats.get('min_down', 0) or 0)
    b_tick = round(b_min_up / b_min_down, 2) if b_min_down > 0 else 0
    
    mkt_conds = [
        {'name': 'gp_body>up', 'passed': body_up > cur_up},
        {'name': 'gp_tick>1', 'passed': tick_ratio > 1.0},
        {'name': 'zq_body>up', 'passed': b_body_up > b_cur_up},
        {'name': 'zq_tick>1', 'passed': b_tick > 1.0}
    ]
    mkt_pass = sum(1 for c in mkt_conds if c['passed'])
    if mkt_pass >= 4:
        signal = 'positive'
    elif mkt_pass >= 2:
        signal = 'cautious'
    else:
        signal = 'wait'
    
    # 7. 逐股评估
    candidates = []
    for stock in stocks:
        code = stock.get('code', '')
        cum_net = float(stock.get('cumulative_main_net', 0) or 0)
        peak_net = float(stock.get('max_cumulative_main_net', 0) or 0)
        chg_pct = stock.get('change_pct')
        consec = int(stock.get('consecutive_attacks', 0) or 0)
        bond_code = stock.get('bond_code', '') or ''
        ind_name = stock.get('industry_name', '') or ''
        
        if chg_pct is None:
            continue
        chg_pct = float(chg_pct)
        
        # 必要条件（全部通过）
        ratio = cum_net / peak_net if peak_net > 0 else 0
        cond_ratio = ratio > 0.9
        cond_chg = chg_pct > 2
        cond_consec = consec > 0
        cond_bond_rank = bond_code != '-' and bond_code != '' and bond_code in bond_rank_set
        
        if not (cond_ratio and cond_chg and cond_consec and cond_bond_rank):
            continue
        
        # 加分条件
        cond_ind = ind_name in top_industries
        bond_data = bond_rank_map.get(bond_code, {})
        bond_chg_val = float(bond_data.get('change_pct', 0) or 0)
        cond_bond_chg = bond_chg_val > 2
        
        bonus = sum([cond_ind, cond_bond_chg])
        level = 1 + min(bonus, 2)
        
        # 只保存 >= 2星
        if level < 2:
            continue
        
        bond_price_val = bond_data.get('price')
        
        candidates.append({
            'code': code,
            'name': stock.get('name', ''),
            'price': stock.get('price'),
            'change_pct': round(chg_pct, 2),
            'bond_code': bond_code,
            'bond_price': float(bond_price_val) if bond_price_val else None,
            'bond_chg': round(bond_chg_val, 2),
            'level': level,
            'cond_ratio': cond_ratio,
            'cond_chg': cond_chg,
            'cond_consec': cond_consec,
            'cond_bond_rank': cond_bond_rank,
            'cond_ind': cond_ind,
            'cond_bond_chg': cond_bond_chg
        })
    
    candidates.sort(key=lambda x: (-x['level'], -x['change_pct']))
    candidates = candidates[:30]
    
    if not candidates:
        continue
    
    # 8. 保存
    with db_engine.connect() as conn:
        for c in candidates:
            record_id = hashlib.md5(f"{c['code']}{save_date}{time_str}".encode()).hexdigest()
            
            conditions = [
                {'name': 'net_ratio>0.9', 'passed': c['cond_ratio']},
                {'name': 'chg>2%', 'passed': c['cond_chg']},
                {'name': 'consec>0', 'passed': c['cond_consec']},
                {'name': 'bond_in_rank', 'passed': c['cond_bond_rank']},
                {'name': 'ind_top10', 'passed': c['cond_ind']},
                {'name': 'bond_chg>2%', 'passed': c['cond_bond_chg']}
            ]
            cond_count = sum(1 for x in conditions if x['passed'])
            
            market_ctx = {
                'signal': signal,
                'passed': mkt_pass,
                'total': 4,
                'conditions': mkt_conds
            }
            
            params = {
                'record_id': record_id,
                'date': save_date,
                'time': time_str,
                'stock_code': c['code'],
                'stock_name': c['name'],
                'stock_price': c['price'],
                'stock_change_pct': c['change_pct'],
                'bond_code': c['bond_code'],
                'bond_price': c['bond_price'],
                'bond_change_pct': c['bond_chg'],
                'level': c['level'],
                'condition_count': cond_count,
                'total_conditions': 6,
                'conditions': json.dumps(conditions),
                'market_context': json.dumps(market_ctx)
            }
            
            conn.execute(insert_sql, params)
            total_inserted += 1
        
        conn.commit()
    
    stars_count = {2: 0, 3: 0}
    for c in candidates:
        stars_count[c['level']] = stars_count.get(c['level'], 0) + 1
    
    print(f"  {time_str}: {len(candidates)} candidates (3star={stars_count.get(3,0)}, 2star={stars_count.get(2,0)})")

# Final verify
with db_engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*), SUM(level=2), SUM(level=3) FROM buy_point_candidates WHERE date = '2026-05-19'"))
    row = result.fetchone()
    print(f"\nTotal: {row[0]} records (2star={row[1]}, 3star={row[2]})")

print("Done!")
