#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查DBProfiler实例状态
"""
from gs2026.dashboard2.middleware.db_profiler import DBProfiler
from gs2026.dashboard.services.data_service import DataService

print('=' * 60)
print('DBProfiler 实例检查')
print('=' * 60)

# 1. 检查DBProfiler单例
print('\n1. DBProfiler单例:')
profiler1 = DBProfiler()
print('   实例ID:', id(profiler1))
print('   enabled:', profiler1.enabled)
print('   _initialized:', profiler1._initialized)
print('   _attached_engines:', profiler1._attached_engines)
print('   queries数量:', len(profiler1.queries))

# 2. 检查DataService中的DBProfiler
print('\n2. DataService实例:')
ds = DataService()
print('   engine ID:', id(ds.engine))

# 3. 再次检查DBProfiler（应该是同一个实例）
print('\n3. 再次获取DBProfiler:')
profiler2 = DBProfiler()
print('   实例ID:', id(profiler2))
print('   是同一个实例:', profiler1 is profiler2)

# 4. 手动触发一个查询
print('\n4. 手动触发查询...')
try:
    from sqlalchemy import text
    with ds.engine.connect() as conn:
        result = conn.execute(text('SELECT 1'))
        print('   查询执行成功')
except Exception as e:
    print('   查询失败:', e)

# 5. 检查查询是否被记录
print('\n5. 检查查询记录:')
print('   queries数量:', len(profiler1.queries))
if profiler1.queries:
    print('   最新查询:', profiler1.queries[-1])

print('\n' + '=' * 60)
