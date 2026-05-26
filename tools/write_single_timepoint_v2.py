"""重新写入单时间点数据（MySQL + Redis DataFrame缓存 + Redis排行）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import logging
logging.disable(logging.WARNING)

import pandas as pd
from sqlalchemy import create_engine, text
from gs2026.utils import config_util, redis_util
from gs2026.monitor.monitor_stock import calculate_industry_topn, save_dataframe_async, shutdown_storage

db_config = config_util.get_config('mysql', 'url')
if isinstance(db_config, dict):
    url = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
else:
    url = db_config
engine = create_engine(url)

DATE_STR = '20260526'
TIME_STR = '10:00:00'
HY_TABLE = f'monitor_hy_top30_{DATE_STR}'
EXPIRE_SECONDS = 86400

# 读取源数据
with engine.connect() as conn:
    all_df = pd.read_sql(f"SELECT * FROM monitor_gp_sssj_{DATE_STR} WHERE time = '{TIME_STR}'", conn)
    top30_df = pd.read_sql(f"SELECT * FROM monitor_gp_top30_{DATE_STR} WHERE time = '{TIME_STR}'", conn)
print(f"all_df: {len(all_df)}, top30: {len(top30_df)}")

# 计算行业排行
result = calculate_industry_topn(top30_df, all_df, DATE_STR, TIME_STR)
print(f"行业结果: {len(result)} 行")

# 清理旧数据
with engine.connect() as conn:
    conn.execute(text(f"DROP TABLE IF EXISTS {HY_TABLE}"))
    conn.commit()

client = redis_util._get_redis_client()
# 清除排行sorted set和hash
client.delete(f'rank:industry:code_{DATE_STR}')
client.delete(f'rank:industry:code_name_{DATE_STR}')
# 清除DataFrame缓存
client.delete(f'{HY_TABLE}:timestamps')
for key in client.keys(f'{HY_TABLE}:*'):
    client.delete(key)
print("已清理 MySQL + Redis")

# 写入（模拟生产流程）
# 1. save_dataframe_async: 写MySQL + Redis DataFrame缓存
save_dataframe_async(result, HY_TABLE, TIME_STR, EXPIRE_SECONDS)

# 2. TOP5 更新Redis排行
top5 = result.head(5)
redis_util.update_rank_redis(top5, 'industry', date_str=DATE_STR)

# 等待异步写入完成
import time
time.sleep(3)
shutdown_storage()

# 验证
print("\n=== 验证 Redis ===")
# 验证排行 sorted set
rank_data = client.zrevrange(f'rank:industry:code_{DATE_STR}', 0, -1, withscores=True)
print(f"Redis排行条数: {len(rank_data)}")
for code, score in rank_data:
    code = code.decode('utf-8') if isinstance(code, bytes) else code
    name = client.hget(f'rank:industry:code_name_{DATE_STR}', code)
    name = name.decode('utf-8') if isinstance(name, bytes) else name
    print(f"  {code}: {name}, count={int(score)}")

# 验证DataFrame缓存
timestamps = client.lrange(f'{HY_TABLE}:timestamps', 0, -1)
print(f"\nRedis timestamps: {[t.decode() if isinstance(t, bytes) else t for t in timestamps]}")

data_json = client.get(f'{HY_TABLE}:{TIME_STR}')
if data_json:
    import json
    data = json.loads(data_json.decode('utf-8') if isinstance(data_json, bytes) else data_json)
    print(f"Redis DataFrame缓存: {len(data)} 行")
    # 检查字段
    if data:
        has_net = 'industry_cumulative_main_net' in data[0]
        print(f"含 industry_cumulative_main_net: {has_net}")
        if has_net:
            for d in data[:3]:
                print(f"  {d['code']}: net={d['industry_cumulative_main_net']:.0f}")
else:
    print("Redis DataFrame缓存: 为空!")

# 验证MySQL
print("\n=== 验证 MySQL ===")
with engine.connect() as conn:
    cnt = pd.read_sql(f"SELECT COUNT(*) as cnt FROM {HY_TABLE}", conn)
    print(f"MySQL行数: {cnt['cnt'].iloc[0]}")

print("\n完成! 请刷新前端验证。")
