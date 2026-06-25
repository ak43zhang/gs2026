import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import pandas as pd

url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

def _safe_read_sql(sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(sql, con=conn)

# 测试 zskj 的 SQL 查询
table_name1 = "data_zsxx_ths"
sql = f"select index_code from {table_name1} where index_code in ('000001','399401')"
print(f"SQL: {sql}")

try:
    df = _safe_read_sql(sql)
    print(f"查询结果: {df.shape}")
    print(df)
    lists = df.values.tolist()
    print(f"lists: {lists}")
    print(f"lists length: {len(lists)}")
except Exception as e:
    print(f"错误: {e}")
