import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 看一条样例
    print('=== analysis_domain_detail_2026 样例 ===')
    r2 = conn.execute(text('SELECT id, content_hash, main_area, child_area, event_time, key_event, importance_score, composite_score, news_type, sectors, concepts, stock_codes FROM analysis_domain_detail_2026 ORDER BY created_at DESC LIMIT 1'))
    cols = list(r2.keys())
    rows = r2.fetchall()
    if rows:
        for col, val in zip(cols, rows[0]):
            val_str = str(val)[:200] if val else 'NULL'
            print(f'  {col:25s} = {val_str}')
    
    # 看get_date_list_until_yesterday函数
    print('\n=== 查找 get_date_list_until_yesterday ===')
