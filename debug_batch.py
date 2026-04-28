"""Debug _get_change_pct_and_main_net_batch"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from sqlalchemy import create_engine, text
from gs2026.dashboard2.config import Config
import pandas as pd

date = '20260428'
time_str = '15:00:00'
stock_codes = ['000539', '002217']

engine = create_engine(Config.MYSQL_URI)
codes_str = ','.join([f"'{c}'" for c in stock_codes])
table_name = f"monitor_gp_sssj_{date}"

query = f"""
    SELECT stock_code, change_pct, main_net_amount
    FROM {table_name}
    WHERE time = '{time_str}' AND stock_code IN ({codes_str})
"""

print(f"SQL: {query}")

with engine.connect() as conn:
    df = pd.read_sql(query, conn)
    print(f"\nDataFrame:\n{df}")
    print(f"\nColumns: {df.columns.tolist()}")
    print(f"\nDtypes:\n{df.dtypes}")
    
    for _, row in df.iterrows():
        code = str(row['stock_code']).zfill(6)
        print(f"\nProcessing code={code}")
        print(f"  change_pct={row['change_pct']}, type={type(row['change_pct'])}")
        print(f"  main_net_amount={row['main_net_amount']}, type={type(row['main_net_amount'])}")
