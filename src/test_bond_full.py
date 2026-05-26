#!/usr/bin/env python
"""测试 monitor_bond.py 的完整数据写入流程"""

import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from datetime import datetime
from gs2026.monitor import monitor_stock as msac
from gs2026.utils import redis_util, config_util

# 初始化 Redis
redis_host = config_util.get_config('common.redis.host')
redis_port = config_util.get_config('common.redis.port')
try:
    redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
    print(f"[OK] Redis 初始化成功: {redis_host}:{redis_port}")
except Exception as e:
    print(f"[FAIL] Redis 初始化失败: {e}")
    sys.exit(1)

# 创建测试数据（模拟债券数据）
date_str = datetime.now().strftime('%Y%m%d')
time_full = datetime.now().strftime('%H:%M:%S')

df = pd.DataFrame({
    'bond_code': ['123001', '123002', '123003'],
    'bond_name': ['测试债券1', '测试债券2', '测试债券3'],
    'price': [100.5, 101.2, 99.8],
    'change_pct': [1.5, 2.1, -0.5],
    'open': [99.0, 100.0, 100.0],
    'time': [time_full, time_full, time_full]
})

print(f"\n测试时间: {date_str} {time_full}")
print(f"测试数据:\n{df}")
print()

# 测试1: 写入 MySQL
table_name = f"monitor_zq_sssj_{date_str}"
expire_seconds = 3600

print(f"测试1: 写入 MySQL 表 {table_name}")
try:
    msac.save_dataframe(df, table_name, time_full, expire_seconds)
    print("[OK] MySQL 写入成功")
except Exception as e:
    print(f"[FAIL] MySQL 写入失败: {e}")
    import traceback
    traceback.print_exc()

print()

# 测试2: 写入 Redis
print(f"测试2: 写入 Redis (键: {table_name}:{time_full})")
try:
    redis_util.save_dataframe_to_redis(df, table_name, time_full, expire_seconds, use_compression=False)
    print("[OK] Redis 写入成功")
except Exception as e:
    print(f"[FAIL] Redis 写入失败: {e}")
    import traceback
    traceback.print_exc()

print()

# 测试3: 从 Redis 读取验证
print(f"测试3: 从 Redis 读取验证")
try:
    df_loaded = redis_util.load_dataframe_by_key(f"{table_name}:{time_full}", use_compression=False)
    if df_loaded is not None and not df_loaded.empty:
        print(f"[OK] Redis 读取成功，共 {len(df_loaded)} 条记录")
        print(f"  读取的数据:\n{df_loaded}")
    else:
        print("[FAIL] Redis 读取失败: 数据为空")
except Exception as e:
    print(f"[FAIL] Redis 读取失败: {e}")
    import traceback
    traceback.print_exc()

print()

# 测试4: 检查 MySQL 表是否存在
print(f"测试4: 检查 MySQL 表是否存在")
try:
    from sqlalchemy import inspect
    from gs2026.monitor.monitor_stock import engine
    inspector = inspect(engine)
    if inspector.has_table(table_name):
        print(f"[OK] 表 {table_name} 存在")
        # 查询表中的记录数
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = result.scalar()
            print(f"  表中记录数: {count}")
    else:
        print(f"[FAIL] 表 {table_name} 不存在")
except Exception as e:
    print(f"[FAIL] 检查表失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*50)
print("测试完成")
print("="*50)
