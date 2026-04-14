#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util
import json

redis_util.init_redis(host='localhost', port=6379, decode_responses=True)
client = redis_util._get_redis_client()

date = '20260414'
sssj_table = f"monitor_zq_sssj_{date}"
data_key = f"{sssj_table}:sssj_data"

# 获取一条数据查看结构
all_data = client.hgetall(data_key)
print(f"总数据条数: {len(all_data)}")

# 查看第一条数据的结构
for code, data_json in list(all_data.items())[:1]:
    print(f"\n债券代码: {code}")
    data = json.loads(data_json)
    print(f"数据字段: {list(data.keys())}")
    print(f"数据内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
