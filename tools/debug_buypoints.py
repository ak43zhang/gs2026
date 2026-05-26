# debug_buypoints.py - Check what data buy-points API actually gets
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard.services import data_service

date = '20260518'
time_str = '09:51:06'

# 1. Check stock ranking at time
print('=== Stock ranking at 09:51:06 ===')
stocks = data_service.get_ranking_at_time(
    asset_type='stock', limit=10, date=date, time_str=time_str)
if stocks:
    print(f'Count: {len(stocks)}')
    # Show first stock's keys
    print(f'Keys: {list(stocks[0].keys())}')
    # Find 300608
    for s in stocks:
        if '300608' in str(s.get('code', '')):
            print(f'FOUND 300608: {json.dumps(s, ensure_ascii=False, default=str)[:300]}')
            break
    else:
        print('300608 NOT in top 10, checking all...')
        all_stocks = data_service.get_ranking_at_time(
            asset_type='stock', limit=500, date=date, time_str=time_str)
        if all_stocks:
            for s in all_stocks:
                if '300608' in str(s.get('code', '')):
                    print(f'FOUND 300608 at rank: {json.dumps(s, ensure_ascii=False, default=str)[:300]}')
                    break
            else:
                print(f'300608 NOT found in {len(all_stocks)} stocks')
        else:
            print('No stocks returned at all')
    # Show sample
    if stocks:
        print(f'Sample[0]: {json.dumps(stocks[0], ensure_ascii=False, default=str)[:300]}')
else:
    print('No stock ranking data returned')

# 2. Check industry ranking at time
print('\n=== Industry ranking at 09:51:06 ===')
ind = data_service.get_ranking_at_time(
    asset_type='industry', limit=10, date=date, time_str=time_str)
if ind:
    print(f'Count: {len(ind)}')
    print(f'Keys: {list(ind[0].keys())}')
    for i in ind[:3]:
        print(f'  {i.get("name", i.get("industry_name", "?"))}: count={i.get("count")}')
else:
    print('No industry ranking data')

# 3. Check market stats at time
print('\n=== Market stats at 09:51:06 ===')
mkt = data_service.get_market_stats(date=date, use_mysql=True, time_str=time_str)
if mkt:
    st = mkt.get('stock', {})
    print(f'body_up={st.get("body_up")}, cur_up={st.get("cur_up")}, min_up={st.get("min_up")}, min_down={st.get("min_down")}')
else:
    print('No market stats')
