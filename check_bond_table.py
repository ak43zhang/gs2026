from sqlalchemy import create_engine
import pandas as pd

url = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs'
engine = create_engine(url)

# 检查债券表结构
df = pd.read_sql('SHOW COLUMNS FROM monitor_zq_top30_20260415', engine)
print('monitor_zq_top30_20260415 表结构:')
print(df[['Field', 'Type']].to_string())

# 检查行业表结构
df2 = pd.read_sql('SHOW COLUMNS FROM monitor_hy_top30_20260415', engine)
print('\nmonitor_hy_top30_20260415 表结构:')
print(df2[['Field', 'Type']].to_string())

# 查询债券表样本数据
df3 = pd.read_sql('SELECT * FROM monitor_zq_top30_20260415 LIMIT 3', engine)
print('\n债券表样本数据:')
print(df3.to_string())