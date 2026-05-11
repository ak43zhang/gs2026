# -*- coding: utf-8 -*-
"""诊断 Redis hset 报错原因"""
import sys, json, redis
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

# 1. Redis 版本信息
print('=== Redis 环境 ===')
r = redis.Redis(host='localhost', port=6379, decode_responses=False)
info = r.info('server')
print(f"  Redis 服务端版本: {info.get('redis_version', '未知')}")
print(f"  redis-py 版本: {redis.__version__}")
print()

# 2. 测试各种 mapping 情况
test_cases = [
    ('正常dict', {'a': 'hello', 'b': '123'}),
    ('含None值str', {'a': 'hello', 'b': 'None'}),
    ('空字符串值', {'a': '', 'b': 'test'}),
    ('中文值', {'名称': '测试股票', '代码': '600001'}),
    ('JSON字符串值', {'data': json.dumps(['板块A', '板块B'], ensure_ascii=False)}),
    ('空dict', {}),
    ('单键', {'only_key': 'only_val'}),
]

print('=== hset mapping 测试 ===')
for name, mapping in test_cases:
    test_key = f'_diag_test:{name}'
    try:
        if mapping:
            r.hset(test_key, mapping=mapping)
            print(f'  {name}: OK (写入{len(mapping)}个字段)')
        else:
            r.hset(test_key, mapping=mapping)
            print(f'  {name}: OK (空dict居然成功了)')
    except Exception as e:
        print(f'  {name}: FAILED - {type(e).__name__}: {e}')
    finally:
        r.delete(test_key)

# 3. 模拟真实 record
print('\n=== 模拟涨停 record ===')
fake_record = {
    'content_hash': 'abc123',
    'stock_name': '测试股票',
    'stock_code': '600001',
    'trade_date': '2026-05-06',
    'zt_time': '09:30:00',
    'zt_time_range': 'auction',
    'stock_nature': '',
    'lhb_analysis': '',
    'sector_msg': json.dumps([], ensure_ascii=False),
    'concept_msg': json.dumps([], ensure_ascii=False),
    'leading_stock_msg': json.dumps([], ensure_ascii=False),
    'influence_msg': json.dumps([], ensure_ascii=False),
    'expect_msg': json.dumps([], ensure_ascii=False),
    'deep_analysis': json.dumps([], ensure_ascii=False),
    'sectors': json.dumps([], ensure_ascii=False),
    'concepts': json.dumps([], ensure_ascii=False),
    'leading_stocks': json.dumps([], ensure_ascii=False),
    'has_expect': 0,
    'continuity': 0,
    'analysis_version': '1.0.0',
}
mapping = {k: str(v) for k, v in fake_record.items()}
print(f'  record 字段数: {len(fake_record)}')
print(f'  mapping 字段数: {len(mapping)}')
print(f'  空值字段: {[k for k, v in mapping.items() if not v]}')

try:
    r.hset('_diag_test:full_record', mapping=mapping)
    print('  写入: OK')
except Exception as e:
    print(f'  写入: FAILED - {e}')
finally:
    r.delete('_diag_test:full_record')

print('\ndone')
