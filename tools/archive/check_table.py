import sys
sys.path.insert(0, 'src')
from gs2026.utils import config_util
from sqlalchemy import create_engine, inspect

url = config_util.get_config('common.url')
engine = create_engine(url)

# 查看表结构
inspector = inspect(engine)
columns = inspector.get_columns('data_bond_daily')
print('data_bond_daily 表结构:')
for col in columns:
    print(f"  {col['name']}: {col['type']}")
