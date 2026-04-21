#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util
import json

redis_util.init_redis(host='localhost', port=6379, decode_responses=True)
client = redis_util._get_redis_client()

# 获取最新的一个时间点的数据
key = "monitor_zq_apqd_20260414:09:30:03"
data_json = client.get(key)

if data_json:
    data = json.loads(data_json)
    print(f"数据类型: {type(data)}")
    if isinstance(data, list) and len(data) > 0:
        print(f"列表长度: {len(data)}")
        print(f"第一条数据字段: {list(data[0].keys())}")
        print(f"第一条数据: {json.dumps(data[0], ensure_ascii=False, indent=2)}")
    elif isinstance(data, dict):
        print(f"数据字段: {list(data.keys())}")
        print(f"数据内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
else:
    print("无数据")
