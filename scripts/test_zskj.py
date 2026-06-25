import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import pandas as pd

url = config_util.get_config('common.url')
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

print('Testing data_zsxx_ths query...')
sql = "SELECT index_code FROM data_zsxx_ths WHERE index_code IN ('000001','399401')"
print(f'SQL: {sql}')

with engine.connect() as conn:
    df = pd.read_sql(sql, con=conn)
    print(f'Result: {df.shape}')
    print(df)
print('Done')
