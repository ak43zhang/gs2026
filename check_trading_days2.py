import pandas as pd
from sqlalchemy import create_engine

url = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs'
engine = create_engine(url)

sql = "SELECT trade_date FROM data_jyrl WHERE trade_status = 1 AND trade_date BETWEEN '2026-04-01' AND '2026-04-30' ORDER BY trade_date"
df = pd.read_sql(sql, engine)
print('2026年4月交易日:')
print(df.to_string())
print(f'\n共 {len(df)} 个交易日')