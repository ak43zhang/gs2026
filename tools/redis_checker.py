#!/usr/bin/env python3
"""
Redis检查工具
检查Redis键、数据、过期情况

使用示例:
    python tools/redis_checker.py --pattern "monitor_zq*20260421*"
    python tools/redis_checker.py --pattern "domain:*" --stats
    python tools/redis_checker.py --check-keys --count 100
"""
import sys
sys.path.insert(0, 'src')

import argparse
from collections import defaultdict
from gs2026.utils import redis_util


def check_keys_by_pattern(pattern: str, stats: bool = False):
    """按模式检查Redis键"""
    redis_client = redis_util.get_redis_client()
    
    print(f"\n=== Redis键匹配: {pattern} ===")
    
    keys = []
    cursor = 0
    while True:
        cursor, batch = redis_client.scan(cursor, match=pattern, count=1000)
        keys.extend(batch)
        if cursor == 0:
            break
    
    print(f"找到 {len(keys)} 个键")
    
    if not keys:
        return
    
    if stats:
        # 按前缀统计
        prefix_count = defaultdict(int)
        for key in keys:
            if ':' in key:
                prefix = key.split(':')[0]
            else:
                prefix = key.split('_')[0] if '_' in key else 'other'
            prefix_count[prefix] += 1
        
        print(f"\n按前缀统计:")
        for prefix, count in sorted(prefix_count.items(), key=lambda x: -x[1]):
            print(f"  {prefix}: {count}")
    
    # 显示前10个键的详细信息
    print(f"\n前10个键详情:")
    for key in keys[:10]:
        key_type = redis_client.type(key)
        ttl = redis_client.ttl(key)
        ttl_str = f"{ttl}s" if ttl > 0 else "永不过期" if ttl == -1 else "已过期"
        
        if key_type == 'string':
            size = redis_client.strlen(key)
        elif key_type == 'hash':
            size = redis_client.hlen(key)
        elif key_type == 'list':
            size = redis_client.llen(key)
        elif key_type == 'set':
            size = redis_client.scard(key)
        elif key_type == 'zset':
            size = redis_client.zcard(key)
        else:
            size = '?'
        
        print(f"  {key} [{key_type}] 大小:{size} TTL:{ttl_str}")


def check_memory_usage():
    """检查内存使用"""
    redis_client = redis_util.get_redis_client()
    
    print(f"\n=== Redis内存使用 ===")
    
    info = redis_client.info('memory')
    used = info.get('used_memory_human', 'N/A')
    peak = info.get('used_memory_peak_human', 'N/A')
    
    print(f"当前使用: {used}")
    print(f"峰值使用: {peak}")


def main():
    parser = argparse.ArgumentParser(description='Redis检查工具')
    parser.add_argument('--pattern', help='键匹配模式')
    parser.add_argument('--stats', action='store_true', help='显示统计')
    parser.add_argument('--memory', action='store_true', help='检查内存')
    parser.add_argument('--count', type=int, default=100, help='扫描数量')
    
    args = parser.parse_args()
    
    if args.pattern:
        check_keys_by_pattern(args.pattern, args.stats)
    elif args.memory:
        check_memory_usage()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
