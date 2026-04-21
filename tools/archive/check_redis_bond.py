#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util
from datetime import datetime, timedelta

redis_util.init_redis(host='localhost', port=6379, decode_responses=True)
client = redis_util._get_redis_client()

date = '20260414'

# 检查时间戳列表
sssj_table = f"monitor_zq_sssj_{date}"
ts_key = f"{sssj_table}:timestamps"
print(f"检查 {ts_key}")

timestamps = client.lrange(ts_key, 0, 10)
print(f"时间戳列表: {timestamps}")

# 检查3秒区间内的数据
if timestamps:
    latest_ts = timestamps[0]
    print(f"\n最新时间戳: {latest_ts}")
    
    query_dt = datetime.strptime(f"{date} {latest_ts}", "%Y%m%d %H:%M:%S")
    start_time = (query_dt - timedelta(seconds=3)).strftime("%H:%M:%S")
    end_time = latest_ts
    
    print(f"3秒区间: {start_time} - {end_time}")
    
    # 检查sorted set
    zset_key = f"{sssj_table}:attack_times"
    print(f"\n检查 {zset_key}")
    
    start_score = int(start_time.replace(":", ""))
    end_score = int(end_time.replace(":", ""))
    
    attack_records = client.zrangebyscore(zset_key, start_score, end_score, withscores=True)
    print(f"3秒区间内的上攻记录: {len(attack_records)} 条")
    for record, score in attack_records[:10]:
        print(f"  {record} (score: {score})")
