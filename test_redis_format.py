#!/usr/bin/env python3
"""
检查Redis数据格式
"""
import redis
import pickle
import zlib

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)

# 获取一个key
keys = redis_client.keys('monitor_gp_sssj_20260429:*')[:3]

for key in keys:
    print(f"\nKey: {key}")
    data = redis_client.get(key)
    print(f"  数据类型: {type(data)}")
    print(f"  数据长度: {len(data)}")
    print(f"  前50字节: {data[:50]}")
    
    # 尝试解压
    try:
        decompressed = zlib.decompress(data)
        print(f"  解压后长度: {len(decompressed)}")
        df = pickle.loads(decompressed)
        print(f"  成功: DataFrame {df.shape}")
        print(f"  列: {list(df.columns)}")
    except Exception as e:
        print(f"  解压失败: {e}")
        # 尝试直接pickle
        try:
            df = pickle.loads(data)
            print(f"  直接pickle成功: DataFrame {df.shape}")
        except Exception as e2:
            print(f"  pickle也失败: {e2}")

redis_client.close()
