from sqlalchemy import create_engine
from gs2026.utils import config_util
import pandas as pd

url = config_util.get_config('common.url')
engine = create_engine(url)

df1 = pd.read_sql("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_NAME='news_cls2026'", engine)
print('news_cls2026:', df1['COLUMN_NAME'].tolist())

df2 = pd.read_sql("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_NAME='news_combine2026'", engine)
print('news_combine2026:', df2['COLUMN_NAME'].tolist())
