"""
完整模拟买点候选流程：以09:30:21为例
调用真实的数据增强函数，确保数据完全正确
"""
import sys, json, hashlib
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from sqlalchemy import text
from datetime import datetime
from gs2026.dashboard.services.data_service import DataService
from gs2026.utils.stock_bond_mapping_cache import get_cache

data_service = DataService()
cache = get_cache()

date = '20260519'
time_str = '09:30:21'

print(f"=== 模拟买点候选 {date} {time_str} ===\n")

# ========== 1. 获取大盘数据 ==========
market_data = data_service.get_market_stats(date=date, use_mysql=True, time_str=time_str)
stock_stats = market_data.get('stock', {}) if market_data else {}

body_up = float(stock_stats.get('body_up', 0) or 0)
cur_up = float(stock_stats.get('cur_up', 0) or 0)
min_up = float(stock_stats.get('min_up', 0) or 0)
min_down = float(stock_stats.get('min_down', 0) or 0)
tick_ratio = round(min_up / min_down, 2) if min_down > 0 else 0
strength = float(stock_stats.get('strength_score', 0) or 0)

print(f"[1] 大盘: body_up={body_up}, cur_up={cur_up}, min_up={min_up}, min_down={min_down}, tick={tick_ratio}, strength={strength}")

# ========== 2. 评估大盘条件 ==========
market_conditions = []
market_conditions.append({'name': 'body>up', 'passed': body_up > cur_up, 'detail': f'{int(body_up)} vs {int(cur_up)}'})
market_conditions.append({'name': 'tick>1.0', 'passed': tick_ratio > 1.0, 'detail': f'tick {tick_ratio}'})

passed_count = sum(1 for c in market_conditions if c['passed'])
total_count = len(market_conditions)
if total_count == 0 or passed_count >= total_count * 0.8:
    market_signal = 'positive'
elif passed_count >= total_count * 0.6:
    market_signal = 'cautious'
else:
    market_signal = 'wait'

print(f"[2] 大盘信号: {market_signal} ({passed_count}/{total_count})")
for mc in market_conditions:
    print(f"    {mc['name']}: {'PASS' if mc['passed'] else 'FAIL'} ({mc['detail']})")

# ========== 3. 获取股票排行 ==========
stocks = data_service.get_ranking_at_time(asset_type='stock', limit=500, date=date, time_str=time_str)
print(f"\n[3] 股票排行: {len(stocks)} stocks")

# ========== 3.5 补充债券/行业信息 ==========
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

# ========== 3.6 补充涨跌幅和主力净额（关键！）==========
# 直接从monitor_gp_sssj表查询
from sqlalchemy import create_engine
import pandas as pd

db_engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

codes_str = ','.join([f"'{c}'" for c in stock_codes])
table_name = f"monitor_gp_sssj_{date}"

try:
    with db_engine.connect() as conn:
        query = text(f"""
            SELECT stock_code, change_pct, cumulative_main_net, max_cumulative_main_net, price
            FROM {table_name}
            WHERE time = '{time_str}' AND stock_code IN ({codes_str})
        """)
        df = pd.read_sql(query, conn)
        
        if not df.empty:
            df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
            change_pct_map = dict(zip(df['stock_code'], df['change_pct'].astype(float)))
            main_net_map = dict(zip(df['stock_code'], df['cumulative_main_net'].fillna(0).astype(float)))
            peak_map = dict(zip(df['stock_code'], df['max_cumulative_main_net'].fillna(0).astype(float)))
            price_map = dict(zip(df['stock_code'], df['price'].fillna(0).astype(float)))
        else:
            change_pct_map, main_net_map, peak_map, price_map = {}, {}, {}, {}
except Exception as e:
    print(f"  Query error: {e}")
    change_pct_map, main_net_map, peak_map, price_map = {}, {}, {}, {}

# 将数据填充回stocks
for stock in stocks:
    code = stock.get('code', '')
    stock['change_pct'] = change_pct_map.get(code)
    stock['cumulative_main_net'] = main_net_map.get(code, 0)
    stock['max_cumulative_main_net'] = peak_map.get(code, 0)
    stock['price'] = price_map.get(code)

print(f"[3.6] 补充数据: change_pct有{len(change_pct_map)}条, main_net有{len(main_net_map)}条, price有{len(price_map)}条")

# ========== 4. 获取行业排行 ==========
industry_data = data_service.get_ranking_at_time(asset_type='industry', limit=10, date=date, time_str=time_str)
top_industries = set()
if industry_data:
    for ind in industry_data:
        name = ind.get('name', '') or ind.get('industry_name', '')
        if name:
            top_industries.add(name)
print(f"[4] 行业排行: {len(top_industries)} industries")

# ========== 5. 逐股评估 ==========
candidates = []
net_ratio_min = 0.9
change_pct_min = 0
industry_top = 10

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
    cond_ratio = ratio > net_ratio_min if net_ratio_min > 0 else False
    
    ind_name = stock.get('industry_name', '') or ''
    cond_ind = ind_name in top_industries if industry_top > 0 else False
    
    cond_pct = (chg_pct is not None and chg_pct > change_pct_min) if change_pct_min > 0 else False
    
    score = sum([cond_ratio, cond_ind, cond_pct])
    if score > 0:
        candidates.append({
            'code': stock.get('code', ''),
            'name': stock.get('name', ''),
            'price': stock.get('price'),
            'change_pct': round(chg_pct, 2) if chg_pct is not None else None,
            'bond_code': stock.get('bond_code', ''),
            'bond_price': None,
            'bond_chg': None,
            'net_ratio': round(ratio, 3),
            'industry_name': ind_name,
            'cond_net_ratio': cond_ratio,
            'cond_industry': cond_ind,
            'cond_change_pct': cond_pct,
            'score': score
        })

candidates.sort(key=lambda x: (-x['score'], -x['net_ratio']))
candidates = candidates[:30]

print(f"\n[5] 候选结果: {len(candidates)} candidates")
for c in candidates[:10]:
    stars = '*' * c['score']
    bond_mark = f" bond={c['bond_code']}" if c['bond_code'] and c['bond_code'] != '-' else ""
    print(f"  {c['code']} {c['name']} price={c['price']} chg={c['change_pct']}% ratio={c['net_ratio']}{bond_mark} {stars}")

# ========== 6. 保存到数据库 ==========
if candidates:
    from sqlalchemy import create_engine
    engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')
    
    # 先删除今天的测试数据
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM buy_point_candidates WHERE date = '2026-05-19'"))
        conn.commit()
    
    save_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    save_time = time_str
    
    sql = """
        INSERT INTO buy_point_candidates 
        (record_id, date, time, stock_code, stock_name, stock_price, stock_change_pct,
         bond_code, bond_price, bond_change_pct, level, condition_count, total_conditions,
         conditions, market_context)
        VALUES (:record_id, :date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,
         :bond_code, :bond_price, :bond_change_pct, :level, :condition_count, :total_conditions,
         :conditions, :market_context)
        ON DUPLICATE KEY UPDATE
        stock_price=VALUES(stock_price), stock_change_pct=VALUES(stock_change_pct),
        level=VALUES(level)
    """
    
    with engine.connect() as conn:
        for c in candidates:
            code = c.get('code', '')
            record_id = hashlib.md5(f"{code}{save_date}{save_time}".encode()).hexdigest()
            
            score = c.get('score', 0)
            level = 3 if score >= 3 else (2 if score >= 2 else 1)
            
            conditions = [
                {'name': 'net_ratio', 'passed': bool(c.get('cond_net_ratio'))},
                {'name': 'industry', 'passed': bool(c.get('cond_industry'))},
                {'name': 'change_pct', 'passed': bool(c.get('cond_change_pct'))}
            ]
            condition_count = sum(1 for x in conditions if x['passed'])
            
            market_ctx = {
                'signal': market_signal,
                'passed': passed_count,
                'total': total_count
            }
            
            params = {
                'record_id': record_id,
                'date': save_date,
                'time': save_time,
                'stock_code': code,
                'stock_name': c.get('name', ''),
                'stock_price': c.get('price'),
                'stock_change_pct': c.get('change_pct'),
                'bond_code': c.get('bond_code') if c.get('bond_code') != '-' else '',
                'bond_price': c.get('bond_price'),
                'bond_change_pct': c.get('bond_chg'),
                'level': level,
                'condition_count': condition_count,
                'total_conditions': 3,
                'conditions': json.dumps(conditions),
                'market_context': json.dumps(market_ctx)
            }
            
            conn.execute(text(sql), params)
        
        conn.commit()
    
    # 验证
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM buy_point_candidates WHERE date = '2026-05-19'"))
        count = result.fetchone()[0]
        print(f"\n[6] Saved: {count} records for 2026-05-19")
else:
    print("\n[6] No candidates to save")

print("\nDone!")
