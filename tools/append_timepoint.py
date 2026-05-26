"""追加一个时间点的行业数据（不删除已有数据）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import logging
logging.disable(logging.WARNING)

import pandas as pd
from sqlalchemy import create_engine
from gs2026.utils import config_util, redis_util
from gs2026.monitor.monitor_stock import calculate_industry_topn, save_dataframe_async, shutdown_storage

db_config = config_util.get_config('mysql', 'url')
if isinstance(db_config, dict):
    url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
else:
    url = db_config
engine = create_engine(url)

DATE_STR = '20260526'
TIME_STR = '10:00:03'
HY_TABLE = f'monitor_hy_top30_{DATE_STR}'
EXPIRE_SECONDS = 86400

# 读取源数据
with engine.connect() as conn:
    all_df = pd.read_sql(f"SELECT * FROM monitor_gp_sssj_{DATE_STR} WHERE time = '{TIME_STR}'", conn)
    top30_df = pd.read_sql(f"SELECT * FROM monitor_gp_top30_{DATE_STR} WHERE time = '{TIME_STR}'", conn)
print(f"all_df: {len(all_df)}, top30: {len(top30_df)}")

if all_df.empty:
    print(f"ERROR: {TIME_STR} 无数据!")
    sys.exit(1)

# 计算行业排行
result = calculate_industry_topn(top30_df, all_df, DATE_STR, TIME_STR)
print(f"行业结果: {len(result)} 行")

# 写入（追加，不删除已有数据）
# 1. save_dataframe_async: 写MySQL(append) + Redis DataFrame缓存
save_dataframe_async(result, HY_TABLE, TIME_STR, EXPIRE_SECONDS)

# 2. TOP5 更新Redis排行（累加）
top5 = result.head(5)
redis_util.update_rank_redis(top5, 'industry', date_str=DATE_STR)

import time
time.sleep(3)
shutdown_storage()

# 验证
print("\n=== 验证 ===")
client = redis_util._get_redis_client()

# Redis排行（累计）
rank_data = client.zrevrange(f'rank:industry:code_{DATE_STR}', 0, -1, withscores=True)
print(f"Redis排行条数: {len(rank_data)}")
for code, score in rank_data:
    code = code.decode('utf-8') if isinstance(code, bytes) else code
    name = client.hget(f'rank:industry:code_name_{DATE_STR}', code)
    name = name.decode('utf-8') if isinstance(name, bytes) else name
    print(f"  {code}: {name}, count={int(score)}")

# Redis timestamps
timestamps = client.lrange(f'{HY_TABLE}:timestamps', 0, -1)
ts_list = [t.decode() if isinstance(t, bytes) else t for t in timestamps]
print(f"\nRedis timestamps: {ts_list}")

# MySQL
with engine.connect() as conn:
    cnt = pd.read_sql(f"SELECT time, COUNT(*) as cnt FROM {HY_TABLE} GROUP BY time ORDER BY time", conn)
    print(f"\nMySQL:")
    for _, row in cnt.iterrows():
        print(f"  {row['time']}: {row['cnt']} 行")

print("\n完成!")
