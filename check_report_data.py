"""分析4张表的数据量和分数分布"""
from sqlalchemy import create_engine
from gs2026.utils import config_util
import pandas as pd

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    print('=== 各表数据量 ===')
    for t in ['analysis_domain_detail_2026', 'analysis_news_detail_2026', 'analysis_notice_detail_2026', 'analysis_ztb_detail_2026']:
        cnt = pd.read_sql(f'SELECT COUNT(1) as cnt FROM {t}', conn).iloc[0]['cnt']
        print(f'{t}: {cnt}条')

    print('\n=== domain 利好数据 top5 ===')
    df = pd.read_sql("SELECT composite_score, news_type, news_size, key_event FROM analysis_domain_detail_2026 WHERE news_type='利好' ORDER BY composite_score DESC LIMIT 5", conn)
    for _, r in df.iterrows():
        print(f"  score={r['composite_score']} size={r['news_size']} | {str(r['key_event'])[:60]}")

    print('\n=== news 利好数据 top5 ===')
    df = pd.read_sql("SELECT composite_score, news_type, news_size, title FROM analysis_news_detail_2026 WHERE news_type='利好' ORDER BY composite_score DESC LIMIT 5", conn)
    for _, r in df.iterrows():
        print(f"  score={r['composite_score']} size={r['news_size']} | {str(r['title'])[:60]}")

    print('\n=== notice 高分数据 top5 ===')
    df = pd.read_sql("SELECT overnight_score, risk_level, notice_type, stock_name, notice_title FROM analysis_notice_detail_2026 ORDER BY overnight_score DESC LIMIT 5", conn)
    for _, r in df.iterrows():
        print(f"  score={r['overnight_score']} level={r['risk_level']} | {r['stock_name']} {str(r['notice_title'])[:40]}")

    print('\n=== ztb 有预期数据 top5 ===')
    df = pd.read_sql("SELECT has_expect, continuity, stock_name, trade_date, zt_time_range FROM analysis_ztb_detail_2026 WHERE has_expect=1 ORDER BY trade_date DESC LIMIT 5", conn)
    for _, r in df.iterrows():
        print(f"  expect={r['has_expect']} cont={r['continuity']} range={r['zt_time_range']} | {r['stock_name']} {r['trade_date']}")

    # 按日期看各表每日重大利好数量
    print('\n=== 各表每日重大利好数量（最近5天）===')
    print('\n[domain] news_type=利好 AND news_size=重大:')
    df = pd.read_sql("SELECT DATE(event_time) as dt, COUNT(1) as cnt FROM analysis_domain_detail_2026 WHERE news_type='利好' AND news_size='重大' GROUP BY dt ORDER BY dt DESC LIMIT 5", conn)
    print(df.to_string(index=False))

    print('\n[news] news_type=利好 AND news_size=重大:')
    df = pd.read_sql("SELECT DATE(publish_time) as dt, COUNT(1) as cnt FROM analysis_news_detail_2026 WHERE news_type='利好' AND news_size='重大' GROUP BY dt ORDER BY dt DESC LIMIT 5", conn)
    print(df.to_string(index=False))

    print('\n[notice] overnight_score>=80:')
    df = pd.read_sql("SELECT notice_date as dt, COUNT(1) as cnt FROM analysis_notice_detail_2026 WHERE overnight_score>=80 GROUP BY dt ORDER BY dt DESC LIMIT 5", conn)
    print(df.to_string(index=False))

    print('\n[ztb] has_expect=1:')
    df = pd.read_sql("SELECT trade_date as dt, COUNT(1) as cnt FROM analysis_ztb_detail_2026 WHERE has_expect=1 GROUP BY dt ORDER BY dt DESC LIMIT 5", conn)
    print(df.to_string(index=False))
