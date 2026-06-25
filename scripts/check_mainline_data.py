import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT stock_code, stock_name, anomaly_time, mainline_names
        FROM stock_anomaly 
        WHERE trading_date = '2026-06-25' AND ai_status = 'done'
        ORDER BY anomaly_time ASC
    """))
    rows = result.fetchall()
    print(f"总计 {len(rows)} 只已分析股票\n")
    print(f"{'时间':<10} | {'代码':<8} | {'名称':<8} | 主线")
    print("-" * 90)
    for r in rows:
        t = r[2]
        if hasattr(t, 'total_seconds'):
            secs = int(t.total_seconds())
            time_str = f"{secs//3600:02d}:{(secs%3600)//60:02d}:{secs%60:02d}"
        else:
            time_str = str(t)
        ml = r[3] or '(无主线)'
        print(f"{time_str:<10} | {r[0]:<8} | {r[1]:<8} | {ml}")
