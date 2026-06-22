import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 看股票-行业-概念缓存表结构
    r = conn.execute(text('DESCRIBE cache_stock_industry_concept_bond'))
    print('=== cache_stock_industry_concept_bond ===')
    for row in r.fetchall():
        print(f'  {row[0]:25s} {row[1]}')
    
    # 看样例
    r2 = conn.execute(text("SELECT * FROM cache_stock_industry_concept_bond WHERE stock_code='300008' LIMIT 1"))
    rows = r2.fetchall()
    if rows:
        print(f'\nSample for 300008:')
        print(f'  {rows[0]}')
    
    # data_industry_code_component_ths 结构
    r3 = conn.execute(text('DESCRIBE data_industry_code_component_ths'))
    print('\n=== data_industry_code_component_ths ===')
    for row in r3.fetchall():
        print(f'  {row[0]:25s} {row[1]}')
    
    r4 = conn.execute(text('SELECT * FROM data_industry_code_component_ths LIMIT 3'))
    print('\nSamples:')
    for row in r4.fetchall():
        print(f'  {row}')
