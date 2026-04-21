#!/usr/bin/env python3
"""检查 Redis 连接状态"""
import sys
sys.path.insert(0, 'src')

from gs2026.utils import config_util
import redis

host = config_util.get_config('common.redis.host')
port = config_util.get_config('common.redis.port')

print(f"Redis 服务器: {host}:{port}")
print("=" * 50)

try:
    client = redis.Redis(host=host, port=port, socket_timeout=5)
    
    # 检查连接
    client.ping()
    print("✓ Redis 连接正常")
    
    # 客户端信息
    info = client.info('clients')
    print(f"\n客户端连接信息:")
    print(f"  connected_clients: {info.get('connected_clients', 'N/A')}")
    print(f"  blocked_clients: {info.get('blocked_clients', 'N/A')}")
    print(f"  tracking_clients: {info.get('tracking_clients', 'N/A')}")
    
    # 最大连接数
    max_clients = client.config_get('maxclients')
    print(f"  maxclients: {max_clients.get('maxclients', 'N/A')}")
    
    # 连接列表（前20个）
    print(f"\n当前连接列表 (前20个):")
    clients = client.execute_command('CLIENT LIST')
    client_list = clients.decode('utf-8').strip().split('\n')
    for i, c in enumerate(client_list[:20]):
        parts = dict(x.split('=') for x in c.split() if '=' in x)
        print(f"  {i+1}. addr={parts.get('addr', 'N/A')}, age={parts.get('age', 'N/A')}s, idle={parts.get('idle', 'N/A')}s, cmd={parts.get('cmd', 'N/A')}")
    
    if len(client_list) > 20:
        print(f"  ... 还有 {len(client_list) - 20} 个连接")
        
except Exception as e:
    print(f"✗ Redis 连接失败: {e}")
