#!/usr/bin/env python3
"""
缓存管理工具
管理内存缓存和宽表缓存

使用示例:
    python tools/cache_manager.py --warm-up
    python tools/cache_manager.py --reload
    python tools/cache_manager.py --stats
    python tools/cache_manager.py --clear-redis --pattern "domain:*"
"""
import sys
sys.path.insert(0, 'src')

import argparse
from gs2026.dashboard2.services import stock_picker_service
from gs2026.utils import redis_util


def warm_up_cache():
    """预热宽表缓存"""
    print("\n=== 预热宽表缓存 ===")
    try:
        stock_picker_service.warm_up_cache()
        print("✅ 缓存预热完成")
    except Exception as e:
        print(f"❌ 预热失败: {e}")


def reload_memory_cache():
    """重新加载内存缓存"""
    print("\n=== 重新加载内存缓存 ===")
    try:
        stock_picker_service.load_memory_cache()
        
        # 显示统计
        print(f"股票缓存: {len(stock_picker_service._stock_cache)} 只")
        print(f"债券映射: {len(stock_picker_service._bond_map)} 条")
    except Exception as e:
        print(f"❌ 加载失败: {e}")


def show_stats():
    """显示缓存统计"""
    print("\n=== 缓存统计 ===")
    
    # 内存缓存
    stock_count = len(stock_picker_service._stock_cache)
    bond_count = len(stock_picker_service._bond_map)
    
    print(f"\n内存缓存:")
    print(f"  股票数: {stock_count}")
    print(f"  债券映射: {bond_count}")
    
    if stock_count > 0:
        # 有债券的比例
        with_bond = sum(1 for s in stock_picker_service._stock_cache.values() 
                       if s.get('bond_code'))
        print(f"  有债券股票: {with_bond} ({with_bond/stock_count*100:.1f}%)")


def clear_redis_cache(pattern: str):
    """清理Redis缓存"""
    print(f"\n=== 清理Redis缓存: {pattern} ===")
    
    try:
        redis_client = redis_util.get_redis_client()
        
        # 扫描键
        keys = []
        cursor = 0
        while True:
            cursor, batch = redis_client.scan(cursor, match=pattern, count=1000)
            keys.extend(batch)
            if cursor == 0:
                break
        
        print(f"找到 {len(keys)} 个键")
        
        if keys:
            # 删除
            pipe = redis_client.pipeline()
            for key in keys:
                pipe.delete(key)
            pipe.execute()
            print(f"✅ 已删除 {len(keys)} 个键")
        
    except Exception as e:
        print(f"❌ 清理失败: {e}")


def main():
    parser = argparse.ArgumentParser(description='缓存管理工具')
    parser.add_argument('--warm-up', action='store_true', help='预热宽表缓存')
    parser.add_argument('--reload', action='store_true', help='重新加载内存缓存')
    parser.add_argument('--stats', action='store_true', help='显示统计')
    parser.add_argument('--clear-redis', action='store_true', help='清理Redis缓存')
    parser.add_argument('--pattern', default='*', help='Redis键匹配模式')
    
    args = parser.parse_args()
    
    if args.warm_up:
        warm_up_cache()
    elif args.reload:
        reload_memory_cache()
    elif args.stats:
        show_stats()
    elif args.clear_redis:
        clear_redis_cache(args.pattern)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
