"""
测试分布式锁功能
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import time
import redis
from gs2026.utils import config_util, log_util

# 初始化Redis
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_int('common.redis.port')
redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

# 导入锁管理器
from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import (
    DistributedLockManager, 
    with_distributed_lock,
    LockContext
)

logger = log_util.setup_logger("test_distributed_lock")

def test_basic_lock():
    """测试基本锁功能"""
    print("\n=== 测试1: 基本锁功能 ===")
    
    lock_mgr = DistributedLockManager(redis_client, lock_timeout=10)
    
    # 测试加锁
    lock1 = lock_mgr.try_lock("test:lock:001")
    if lock1:
        print("✓ 第一次加锁成功")
    else:
        print("✗ 第一次加锁失败")
        return False
    
    # 测试重复加锁（应失败）
    lock2 = lock_mgr.try_lock("test:lock:001")
    if lock2:
        print("✗ 重复加锁应该失败但却成功")
        return False
    else:
        print("✓ 重复加锁失败（符合预期）")
    
    # 释放锁
    lock_mgr.release_lock(lock1)
    print("✓ 锁已释放")
    
    # 再次加锁（应成功）
    lock3 = lock_mgr.try_lock("test:lock:001")
    if lock3:
        print("✓ 释放后再次加锁成功")
        lock_mgr.release_lock(lock3)
    else:
        print("✗ 释放后再次加锁失败")
        return False
    
    return True

def test_batch_lock():
    """测试批量加锁"""
    print("\n=== 测试2: 批量加锁 ===")
    
    lock_mgr = DistributedLockManager(redis_client, lock_timeout=10)
    
    # 准备测试数据
    items = [
        ["hash001", "内容1"],
        ["hash002", "内容2"],
        ["hash003", "内容3"],
        ["hash004", "内容4"],
        ["hash005", "内容5"],
    ]
    
    # 批量加锁
    locked = lock_mgr.batch_try_lock(
        items,
        key_func=lambda item: f"test:batch:{item[0]}"
    )
    
    print(f"✓ 尝试加锁 {len(items)} 条，成功 {len(locked)} 条")
    
    # 验证已锁定
    for item, lock in locked:
        lock_key = f"test:batch:{item[0]}"
        if lock_mgr.is_locked(lock_key):
            print(f"✓ {item[0]} 已锁定")
        else:
            print(f"✗ {item[0]} 未锁定")
    
    # 释放所有锁
    lock_mgr.release_all()
    print("✓ 所有锁已释放")
    
    return True

def test_filter_locked():
    """测试过滤已锁定"""
    print("\n=== 测试3: 过滤已锁定 ===")
    
    lock_mgr = DistributedLockManager(redis_client, lock_timeout=10)
    
    # 先锁定部分数据
    items = [
        ["hash001", "内容1"],
        ["hash002", "内容2"],
        ["hash003", "内容3"],
    ]
    
    # 锁定第一条
    lock = lock_mgr.try_lock("test:filter:hash001")
    if lock:
        print("✓ hash001 已手动锁定")
    
    # 过滤
    available = lock_mgr.filter_locked(
        items,
        key_func=lambda item: f"test:filter:{item[0]}"
    )
    
    print(f"✓ 原始 {len(items)} 条，过滤后 {len(available)} 条可用")
    
    # 验证hash001不在可用列表
    available_hashes = [item[0] for item in available]
    if "hash001" not in available_hashes:
        print("✓ hash001 已被过滤（符合预期）")
    else:
        print("✗ hash001 未被过滤")
    
    lock_mgr.release_all()
    return True

def test_context_manager():
    """测试上下文管理器"""
    print("\n=== 测试4: 上下文管理器 ===")
    
    # 测试 with_distributed_lock
    with with_distributed_lock(redis_client, "test:ctx:001", lock_timeout=10) as ctx:
        if ctx.acquired:
            print("✓ 上下文管理器获取锁成功")
        else:
            print("✗ 上下文管理器获取锁失败")
            return False
    
    print("✓ 上下文退出后锁已释放")
    
    # 测试 DistributedLockManager 上下文
    with DistributedLockManager(redis_client, lock_timeout=10) as mgr:
        lock = mgr.try_lock("test:ctx:002")
        if lock:
            print("✓ DistributedLockManager 上下文内加锁成功")
        else:
            print("✗ 加锁失败")
            return False
    
    print("✓ 上下文退出后自动释放所有锁")
    
    return True

def test_lock_timeout():
    """测试锁超时"""
    print("\n=== 测试5: 锁超时 ===")
    
    lock_mgr = DistributedLockManager(redis_client, lock_timeout=3)  # 3秒超时
    
    # 加锁
    lock = lock_mgr.try_lock("test:timeout:001")
    if lock:
        print("✓ 加锁成功（3秒后自动过期）")
    
    # 等待4秒
    print("等待4秒...")
    time.sleep(4)
    
    # 检查锁是否已过期
    if not lock_mgr.is_locked("test:timeout:001"):
        print("✓ 锁已自动过期（符合预期）")
    else:
        print("✗ 锁未过期")
    
    return True

def main():
    print("=" * 50)
    print("分布式锁功能测试")
    print("=" * 50)
    
    results = []
    
    try:
        results.append(("基本锁功能", test_basic_lock()))
        results.append(("批量加锁", test_batch_lock()))
        results.append(("过滤已锁定", test_filter_locked()))
        results.append(("上下文管理器", test_context_manager()))
        results.append(("锁超时", test_lock_timeout()))
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\n总计: {passed}/{total} 通过")
    
    # 清理测试锁
    print("\n清理测试数据...")
    for key in redis_client.keys("test:*"):
        redis_client.delete(key)
    print("✓ 清理完成")

if __name__ == '__main__':
    main()
