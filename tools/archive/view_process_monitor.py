"""
查看进程监控Redis数据的工具

运行：python -m gs2026.tools.view_process_monitor
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
from gs2026.utils import redis_util


def main():
    """主函数"""
    print("进程监控Redis数据查看器")
    print("="*60)
    
    # 初始化Redis
    redis_util.init_redis()
    client = redis_util._get_redis_client()
    
    # 获取所有注册进程
    registry_key = "process:registry"
    process_ids = client.smembers(registry_key)
    
    if not process_ids:
        print("Redis中没有注册任何进程")
        return
    
    print(f"注册进程数: {len(process_ids)}")
    print("-"*60)
    
    for pid_bytes in process_ids:
        process_id = pid_bytes.decode('utf-8') if isinstance(pid_bytes, bytes) else pid_bytes
        
        # 获取进程信息
        info_key = f"process:{process_id}"
        info_data = client.get(info_key)
        
        if info_data:
            info = json.loads(info_data.decode('utf-8') if isinstance(info_data, bytes) else info_data)
            
            print(f"\n进程ID: {process_id}")
            print(f"  PID: {info.get('pid')}")
            print(f"  状态: {info.get('status')}")
            print(f"  类型: {info.get('process_type')}")
            print(f"  启动时间: {info.get('start_time')}")
            print(f"  最后心跳: {info.get('last_heartbeat')}")
            
            # 获取心跳数据
            heartbeat_key = f"process:heartbeat:{process_id}"
            heartbeat_data = client.get(heartbeat_key)
            if heartbeat_data:
                heartbeat = json.loads(heartbeat_data.decode('utf-8') if isinstance(heartbeat_data, bytes) else heartbeat_data)
                print(f"  心跳状态: {heartbeat.get('status')}")
        else:
            print(f"\n进程ID: {process_id}")
            print("  信息: 数据不存在")
    
    print("\n" + "="*60)
    
    # 清理选项
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--cleanup', action='store_true', help='清理所有进程数据')
    args = parser.parse_args()
    
    if args.cleanup:
        confirm = input("确定要清理所有进程监控数据吗？(yes/no): ")
        if confirm.lower() == 'yes':
            for pid_bytes in process_ids:
                process_id = pid_bytes.decode('utf-8') if isinstance(pid_bytes, bytes) else pid_bytes
                client.delete(f"process:{process_id}")
                client.delete(f"process:heartbeat:{process_id}")
                client.delete(f"process:{process_id}:auto_restart")
            client.delete(registry_key)
            print("已清理所有数据")


if __name__ == '__main__':
    main()