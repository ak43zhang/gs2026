from sqlalchemy import create_engine
import pandas as pd
import json
from gs2026.utils import config_util

engine = create_engine(config_util.get_config('common.url'))
with engine.connect() as conn:
    # 查看AI应用与智能体主线的股票
    df = pd.read_sql("""SELECT 
        stock_code, stock_name, anomaly_time, 
        price, change_pct, continuous_zt, mainline_names
    FROM stock_anomaly 
    WHERE trading_date = '2026-06-29' 
      AND anomaly_type = 'zt_hit'
    ORDER BY anomaly_time""", conn)
    
    # 筛选AI应用与智能体
    ai_stocks = []
    for _, row in df.iterrows():
        mainlines = row['mainline_names']
        if mainlines and 'AI应用与智能体' in str(mainlines):
            ai_stocks.append(row)
    
    print(f"=== AI应用与智能体主线 ({len(ai_stocks)}只) ===")
    for s in ai_stocks:
        print(f"{s['anomaly_time']} | {s['stock_code']} {s['stock_name']} | 价格{s['price']} | 涨幅{s['change_pct']}% | 连板{s['continuous_zt']}")
