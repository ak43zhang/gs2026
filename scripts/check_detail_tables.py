import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # analysis_news_detail_2026 结构
    print('=== analysis_news_detail_2026 结构 ===')
    r = conn.execute(text('DESCRIBE analysis_news_detail_2026'))
    for row in r.fetchall():
        print(f'  {row[0]:25s} {row[1]}')
    
    # 看一条样例
    print('\n=== news样例 ===')
    r2 = conn.execute(text('SELECT source_table, title, composite_score, news_type, sectors, concepts, leading_stocks FROM analysis_news_detail_2026 WHERE news_type="利好" AND composite_score >= 50 ORDER BY composite_score DESC LIMIT 1'))
    cols = list(r2.keys())
    rows = r2.fetchall()
    if rows:
        for col, val in zip(cols, rows[0]):
            val_str = str(val)[:200] if val else 'NULL'
            print(f'  {col:25s} = {val_str}')
    
    # analysis_notice_detail_2026 结构
    print('\n=== analysis_notice_detail_2026 结构 ===')
    r3 = conn.execute(text('DESCRIBE analysis_notice_detail_2026'))
    for row in r3.fetchall():
        print(f'  {row[0]:25s} {row[1]}')
    
    # 看一条notice样例
    print('\n=== notice样例 ===')
    r4 = conn.execute(text('SELECT stock_code, stock_name, notice_title, overnight_score, notice_type FROM analysis_notice_detail_2026 WHERE overnight_score >= 70 ORDER BY overnight_score DESC LIMIT 1'))
    cols = list(r4.keys())
    rows = r4.fetchall()
    if rows:
        for col, val in zip(cols, rows[0]):
            val_str = str(val)[:200] if val else 'NULL'
            print(f'  {col:25s} = {val_str}')
    
    # 统计各表记录数
    for table in ['analysis_domain_detail_2026', 'analysis_news_detail_2026', 'analysis_notice_detail_2026']:
        r5 = conn.execute(text(f'SELECT COUNT(*) FROM {table}'))
        print(f'\n{table} records: {r5.scalar()}')
