from sqlalchemy import create_engine
import pandas as pd

url = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs'
engine = create_engine(url)

# 查询所有表名
df = pd.read_sql("SHOW TABLES LIKE '%bond%'", engine)
print('包含bond的表:')
print(df.to_string())

df2 = pd.read_sql("SHOW TABLES LIKE '%zq%'", engine)
print('\n包含zq的表:')
print(df2.to_string())

# 检查bond_info表
try:
    df3 = pd.read_sql('SHOW COLUMNS FROM bond_info', engine)
    print('\nbond_info表结构:')
    print(df3[['Field', 'Type']].to_string())
except:
    print('\nbond_info表不存在')
