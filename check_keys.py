#!/usr/bin/env python3
"""检查Redis中的上攻排行key"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import redis_util
from loguru import logger

def check_keys():
    redis_util.init_redis()
    r = redis_util._get_redis_client()
    
    # 查找所有上攻排行相关的key
    keys = r.keys("*attack*20260427*")
    logger.info(f"找到 {len(keys)} 个key")
    
    for key in keys[:20]:
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        logger.info(f"  {key_str}")

if __name__ == "__main__":
    check_keys()
