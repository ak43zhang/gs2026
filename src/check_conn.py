#!/usr/bin/env python
"""检查 Redis 和 MySQL 连接状态"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

from gs2026.utils import redis_util, config_util
from sqlalchemy import create_engine, text

print('=' * 50)
print('检查 Redis 连接')
print('=' * 50)

try:
    redis_host = config_util.get_config('common.redis.host')
    redis_port = config_util.get_config('common.redis.port')
    print(f'Redis 配置: {redis_host}:{redis_port}')

    redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
    redis_client = redis_util._redis_client

    if redis_client:
        info = redis_client.info('clients')
        print(f'Connected clients: {info.get("connected_clients", "N/A")}')
        print(f'Blocked clients: {info.get("blocked_clients", "N/A")}')
        redis_client.ping()
        print('Redis 连接状态: 正常')
    else:
        print('Redis 连接状态: 未连接')
except Exception as e:
    print(f'Redis 错误: {e}')

print()
print('=' * 50)
print('检查 MySQL 连接')
print('=' * 50)

try:
    url = config_util.get_config('common.url')
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

    pool = engine.pool
    print(f'Pool size: {pool.size()}')
    print(f'Checked in: {pool.checkedin()}')
    print(f'Checked out: {pool.checkedout()}')
    print(f'Overflow: {pool.overflow()}')

    with engine.connect() as conn:
        result = conn.execute(text("SHOW STATUS LIKE 'Threads_connected'"))
        row = result.fetchone()
        if row:
            print(f'MySQL Threads_connected: {row[1]}')

        result = conn.execute(text("SHOW STATUS LIKE 'Max_used_connections'"))
        row = result.fetchone()
        if row:
            print(f'MySQL Max_used_connections: {row[1]}')

        result = conn.execute(text('SHOW PROCESSLIST'))
        rows = result.fetchall()
        print(f'当前活跃连接数: {len(rows)}')

        # 统计连接来源
        from collections import Counter
        hosts = [row[2] for row in rows]
        host_counts = Counter(hosts)
        print(f'\n连接来源统计:')
        for host, count in host_counts.most_common():
            print(f'  {host}: {count}')

        # 显示所有连接的详细信息
        print(f'\n所有连接详情:')
        for i, row in enumerate(rows, 1):
            id_, user, host, db, cmd, time_, state, info = row
            info_str = str(info)[:50] if info else 'None'
            print(f'{i}. ID={id_}, User={user}, Host={host}, Cmd={cmd}, Time={time_}s')
            if info_str and info_str != 'None':
                print(f'   Info: {info_str}')

        # 杀掉空闲连接（任何空闲时间）和长时间运行的COMMIT
        print(f'\n杀掉空闲连接和长时间运行的COMMIT...')
        killed = 0
        for row in rows:
            id_, user, host, db, cmd, time_, state, info = row
            # 杀掉任何空闲连接
            if cmd == 'Sleep':
                try:
                    conn.execute(text(f'KILL {id_}'))
                    print(f'  Killed connection {id_} (sleep {time_}s)')
                    killed += 1
                except Exception as e:
                    print(f'  Failed to kill {id_}: {e}')
            # 杀掉长时间运行的COMMIT（超过10分钟）
            elif cmd == 'Query' and info and 'COMMIT' in str(info) and time_ > 600:
                try:
                    conn.execute(text(f'KILL {id_}'))
                    print(f'  Killed connection {id_} (long commit {time_}s)')
                    killed += 1
                except Exception as e:
                    print(f'  Failed to kill {id_}: {e}')
        print(f'共杀掉 {killed} 个连接')

    print('MySQL 连接状态: 正常')
except Exception as e:
    print(f'MySQL 错误: {e}')
    import traceback
    traceback.print_exc()
