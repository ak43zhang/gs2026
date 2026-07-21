"""
测试BondTickCache在Dashboard2上下文中是否能正确访问Redis

模拟Dashboard2启动流程:
1. init_redis() (像Dashboard2的Initializer一样)
2. 测试BondTickCache._redis() 是否返回有效客户端
3. 测试get_bond_ticks() 是否能获取数据
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

print("=" * 60)
print("测试 BondTickCache 纯消费者模式")
print("=" * 60)

# 步骤1：模拟Dashboard2的Redis初始化
print("\n[步骤1] 模拟Dashboard2 init_redis...")
from gs2026.utils import redis_util
if redis_util._redis_client is None:
    redis_util.init_redis()
    print(f"  init_redis() 完成")
else:
    print(f"  Redis已初始化")

print(f"  _redis_client = {redis_util._redis_client}")
print(f"  ping = {redis_util._redis_client.ping()}")

# 步骤2：测试 _get_redis_client
print("\n[步骤2] 测试 _get_redis_client()...")
client = redis_util._get_redis_client()
print(f"  返回值: {client}")
print(f"  是否为None: {client is None}")

# 步骤3：测试 BondTickCache._redis()
print("\n[步骤3] 测试 BondTickCache._redis()...")
from gs2026.redis.bond_tick_cache import BondTickCache, CacheConfig, is_cache_enabled, get_bond_ticks

CacheConfig.ENABLED = True
r = BondTickCache._redis()
print(f"  _redis() 返回: {r}")
print(f"  is_cache_enabled(): {is_cache_enabled()}")

# 步骤4：测试查询测试数据
print("\n[步骤4] 测试 get_bond_ticks('111060', '20260717')...")
import time
start = time.time()
ticks = get_bond_ticks('111060', '20260717')
elapsed = (time.time() - start) * 1000
print(f"  返回条数: {len(ticks)}")
print(f"  耗时: {elapsed:.1f}ms")
if ticks:
    print(f"  首条: {ticks[0]['time']} change_pct={ticks[0]['change_pct']}%")
    print(f"  末条: {ticks[-1]['time']} change_pct={ticks[-1]['change_pct']}%")

# 步骤5：测试盛德转债
print("\n[步骤5] 测试 get_bond_ticks('113064', '20260717')...")
start = time.time()
ticks2 = get_bond_ticks('113064', '20260717')
elapsed2 = (time.time() - start) * 1000
print(f"  返回条数: {len(ticks2)}")
print(f"  耗时: {elapsed2:.1f}ms")
if ticks2:
    print(f"  首条: {ticks2[0]['time']} change_pct={ticks2[0]['change_pct']}%")

# 步骤6：测试不存在的债券
print("\n[步骤6] 测试不存在的债券 get_bond_ticks('999999', '20260717')...")
start = time.time()
ticks3 = get_bond_ticks('999999', '20260717')
elapsed3 = (time.time() - start) * 1000
print(f"  返回条数: {len(ticks3)}")
print(f"  耗时: {elapsed3:.1f}ms")

print("\n" + "=" * 60)
if len(ticks) > 0 and elapsed < 100:
    print("✅ 测试通过！Redis缓存正常工作")
else:
    print("❌ 测试失败！Redis缓存不可用")
    print(f"   ticks={len(ticks)}, elapsed={elapsed:.1f}ms")
print("=" * 60)
