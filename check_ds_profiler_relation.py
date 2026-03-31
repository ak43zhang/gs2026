#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查DataService和DBProfiler的实例关系
"""
from gs2026.dashboard.services.data_service import DataService
from gs2026.dashboard2.middleware.db_profiler import DBProfiler

print('=' * 60)
print('DataService和DBProfiler关系检查')
print('=' * 60)

# 1. 创建第一个DataService
print('\n1. 创建第一个DataService:')
ds1 = DataService()
print('   DataService实例ID:', id(ds1))
print('   engine ID:', id(ds1.engine))

# 检查DBProfiler
profiler = DBProfiler()
print('   DBProfiler实例ID:', id(profiler))
print('   DBProfiler enabled:', profiler.enabled)
print('   _attached_engines:', profiler._attached_engines)
print('   engine ID in _attached_engines:', id(ds1.engine) in profiler._attached_engines)

# 2. 创建第二个DataService（模拟多次导入）
print('\n2. 创建第二个DataService:')
ds2 = DataService()
print('   DataService实例ID:', id(ds2))
print('   engine ID:', id(ds2.engine))
print('   是同一个engine:', ds1.engine is ds2.engine)

# 3. 检查attached_engines
print('\n3. DBProfiler状态:')
print('   _attached_engines:', profiler._attached_engines)
print('   _attached_engines数量:', len(profiler._attached_engines))

# 4. 手动附加引擎
print('\n4. 手动附加ds1的引擎:')
profiler.attach_to_engine(ds1.engine)
print('   _attached_engines:', profiler._attached_engines)

# 5. 执行查询测试
print('\n5. 执行查询测试:')
from sqlalchemy import text
with ds1.engine.connect() as conn:
    result = conn.execute(text('SELECT 2 as num'))
    print('   查询执行成功')

print('\n6. 检查查询记录:')
print('   queries数量:', len(profiler.queries))
if profiler.queries:
    print('   最新查询:', profiler.queries[-1])

print('\n' + '=' * 60)
