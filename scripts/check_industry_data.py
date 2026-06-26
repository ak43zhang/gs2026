import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 1. 行业表
    result = conn.execute(text('SHOW COLUMNS FROM data_industry_code_ths'))
    cols = result.fetchall()
    print('=== data_industry_code_ths ===')
    for c in cols:
        print(f'  {c[0]:30s} {c[1]}')
    result2 = conn.execute(text('SELECT COUNT(*) FROM data_industry_code_ths'))
    print(f'  总记录数: {result2.fetchone()[0]}')
    
    # 2. 行业成分股表
    result3 = conn.execute(text('SHOW COLUMNS FROM data_industry_code_component_ths'))
    cols3 = result3.fetchall()
    print('\n=== data_industry_code_component_ths ===')
    for c in cols3:
        print(f'  {c[0]:30s} {c[1]}')
    result4 = conn.execute(text('SELECT COUNT(*) FROM data_industry_code_component_ths'))
    print(f'  总记录数: {result4.fetchone()[0]}')
    
    # 3. 看几条样例
    result5 = conn.execute(text(
        'SELECT stock_code, stock_name, industry_code, industry_name '
        'FROM data_industry_code_component_ths '
        'LIMIT 5'
    ))
    print('\n=== 成分股样例 ===')
    for r in result5.fetchall():
        print(f'  {r[0]} {r[1]} | {r[2]} {r[3]}')
