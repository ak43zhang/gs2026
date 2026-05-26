#!/usr/bin/env python
"""检查 Redis 和 MySQL 连接状态"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026')

from gs2026.utils import redis_util, config_util
from sqlalchemy import create_engine, text

print("=" * 50)
print("检查 Redis 连接")
print("=" * 50)

try:
    redis_host = config_util.get_config('common.redis.host')
    redis_port = config_util.get_config('common.redis.port')
    print(f"Redis 配置: {redis_host}:{redis_port}")
    
    redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
    redis_client = redis_util._redis_client
    
    if redis_client:
        info = redis_client.info('clients')
        print(f"Connected clients: {info.get('connected_clients', 'N/A')}")
        print(f"Blocked clients: {info.get('blocked_clients', 'N/A')}")
        
        # 检查连接是否可用
        redis_client.ping()
        print("Redis 连接状态: ✓ 正常")
    else:
        print("Redis 连接状态: ✗ 未连接")
except Exception as e:
    print(f"Redis 错误: {e}")

print()
print("=" * 50)
print("检查 MySQL 连接")
print("=" * 50)

try:
    url = config_util.get_config('common.url')
    # 隐藏密码
    display_url = url.replace('://', '://***:***@') if '://' in url else '***'
    print(f"MySQL URL: {display_url}")
    
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    # SQLAlchemy 连接池信息
    pool = engine.pool
    print(f"\n连接池配置:")
    print(f"  Pool size: {pool.size()}")
    print(f"  Checked in: {pool.checkedin()}")
    print(f"  Checked out: {pool.checkedout()}")
    print(f"  Overflow: {pool.overflow()}")
    
    # 查询 MySQL 当前连接数
    with engine.connect() as conn:
        result = conn.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
        row = result.fetchone()
        if row:
            print(f"\nMySQL Threads_connected: {row[1]}")
        
        result = conn.execute(text("SHOW STATUS LIKE 'Max_used_connections'"))
        row = result.fetchone()
        if row:
            print(f"MySQL Max_used_connections: {row[1]}")
        
        # 查询当前连接详情
        result = conn.execute(text("SHOW PROCESSLIST"))
        rows = result.fetchall()
        print(f"\n当前活跃连接数: {len(rows)}")
        
        # 显示前10个连接
        print("\n前10个连接详情:")
        print("-" * 80)
        for i, row in enumerate(rows[:10], 1):
            id_, user, host, db, cmd, time_, state, info = row
            print(f"{i}. ID={id_}, User={user}, Host={host}, DB={db}, Cmd={cmd}, Time={time_}s")
            if info:
                info_str = str(info)[:50] + "..." if len(str(info)) > 50 else str(info)
                print(f"   Info: {info_str}")
        
        if len(rows) > 10:
            print(f"... 还有 {len(rows) - 10} 个连接")
            
    print("\nMySQL 连接状态: ✓ 正常")
    
except Exception as e:
    print(f"MySQL 错误: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 50)
print("检查完成")
print("=" * 50)
