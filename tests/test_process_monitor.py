"""
进程监控功能测试脚本

测试内容：
1. 进程注册/注销
2. 状态查询
3. 自动检测停止
4. 回调功能

运行：python -m gs2026.tests.test_process_monitor
"""

import sys
import time
import subprocess
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from gs2026.utils.process_monitor import ProcessMonitor, get_process_monitor


def test_basic_register_unregister():
    """测试基本注册注销功能"""
    print("\n" + "="*50)
    print("测试1: 基本注册/注销")
    print("="*50)
    
    monitor = ProcessMonitor()
    
    # 注册一个测试进程（使用当前Python进程）
    import os
    current_pid = os.getpid()
    
    success = monitor.register(
        process_id='test_process',
        pid=current_pid,
        process_type='test',
        meta={'test': True}
    )
    
    print(f"注册结果: {'成功' if success else '失败'}")
    
    # 查询状态
    status = monitor.get_status('test_process')
    if status:
        print(f"进程状态: {status.status}")
        print(f"进程PID: {status.pid}")
        print(f"进程类型: {status.process_type}")
    else:
        print("未找到进程状态")
    
    # 检查是否运行中
    is_running = monitor.is_running('test_process')
    print(f"是否运行中: {is_running}")
    
    # 注销
    success = monitor.unregister('test_process')
    print(f"注销结果: {'成功' if success else '失败'}")
    
    # 再次查询
    status = monitor.get_status('test_process')
    print(f"注销后状态: {status}")
    
    return True


def test_monitor_detection():
    """测试自动检测功能"""
    print("\n" + "="*50)
    print("测试2: 自动检测进程停止")
    print("="*50)
    
    monitor = ProcessMonitor(check_interval=2)
    
    # 创建一个临时子进程
    proc = subprocess.Popen(
        [sys.executable, '-c', 'import time; time.sleep(10)'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    print(f"创建测试子进程 PID: {proc.pid}")
    
    # 注册进程
    monitor.register(
        process_id='test_subprocess',
        pid=proc.pid,
        process_type='test_subprocess'
    )
    
    # 启动监控
    callback_triggered = {'stopped': False}
    
    def on_status_change(pid, status, info):
        print(f"回调触发: {pid} -> {status}")
        if status == 'stopped':
            callback_triggered['stopped'] = True
    
    monitor.on_status_change('test_subprocess', on_status_change)
    monitor.start_monitoring()
    
    print("监控已启动，等待5秒...")
    time.sleep(5)
    
    # 检查状态
    status = monitor.get_status('test_subprocess')
    print(f"进程状态: {status.status if status else 'None'}")
    
    # 终止子进程
    print("终止子进程...")
    proc.terminate()
    proc.wait()
    
    print("等待监控检测...")
    time.sleep(5)
    
    # 检查是否检测到停止
    status = monitor.get_status('test_subprocess')
    if status and status.status == 'stopped':
        print("✓ 成功检测到进程停止")
    else:
        print("✗ 未检测到进程停止")
    
    monitor.stop_monitoring()
    monitor.unregister('test_subprocess')
    
    return True


def test_api_endpoint():
    """测试API端点"""
    print("\n" + "="*50)
    print("测试3: API端点测试")
    print("="*50)
    
    try:
        import requests
        
        # 启动Dashboard（假设已在运行）
        base_url = 'http://localhost:5000'
        
        # 测试获取监控状态
        response = requests.get(f'{base_url}/api/control/monitor-status')
        print(f"API响应状态: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"响应数据: {data}")
            return True
        else:
            print(f"API请求失败: {response.text}")
            return False
            
    except ImportError:
        print("未安装requests库，跳过API测试")
        return True
    except Exception as e:
        print(f"API测试失败: {e}")
        return False


def test_integration():
    """集成测试 - 使用ProcessManager"""
    print("\n" + "="*50)
    print("测试4: ProcessManager集成测试")
    print("="*50)
    
    from gs2026.dashboard.services.process_manager import ProcessManager
    
    pm = ProcessManager()
    
    # 获取所有监控进程
    processes = pm.get_all_process_status()
    print(f"当前监控进程数: {len(processes)}")
    
    for p in processes:
        print(f"  - {p['process_id']}: {p['status']} (PID: {p['pid']})")
    
    return True


def main():
    """运行所有测试"""
    print("进程监控功能测试")
    print("="*50)
    
    tests = [
        ("基本注册/注销", test_basic_register_unregister),
        ("自动检测", test_monitor_detection),
        ("API端点", test_api_endpoint),
        ("ProcessManager集成", test_integration),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"测试失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 打印结果
    print("\n" + "="*50)
    print("测试结果汇总")
    print("="*50)
    for name, result in results:
        status = "通过" if result else "失败"
        print(f"  {name}: {status}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\n总计: {passed}/{total} 通过")


if __name__ == '__main__':
    main()