#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接从Redis获取数据，使用直接连接
"""
import redis
import json
import zlib

# 直接连接Redis
try:
    client = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=False)
    client.ping()
    print("Redis连接成功")
except Exception as e:
    print(f"Redis连接失败: {e}")
    exit(1)

sssj_table = 'monitor_gp_sssj_20250626'
codes = ['688596', '688300', '600481']

for time_str in ['10:00:15', '10:00:18']:
    print(f'\n{"="*60}')
    print(f'时间: {time_str}')
    print(f'{"="*60}')
    
    redis_key = f'{sssj_table}:{time_str}'
    data = client.get(redis_key)
    
    if data is None:
        print('数据不存在')
        continue
    
    # 尝试解压
    try:
        # 先尝试作为JSON解析
        json_str = data.decode('utf-8')
        records = json.loads(json_str)
    except:
        # 尝试解压
        try:
            json_str = zlib.decompress(data).decode('utf-8')
            records = json.loads(json_str)
        except Exception as e:
            print(f'解析失败: {e}')
            continue
    
    if not records:
        print('数据为空')
        continue
    
    # 检查第一条记录的列名
    print(f'\n所有列名: {list(records[0].keys())}')
    
    # 查找指定股票
    print(f'\n{"-"*60}')
    print(f'股票详情:')
    print(f'{"-"*60}')
    
    for code in codes:
        # 查找股票
        stock_records = [r for r in records if str(r.get('stock_code', r.get('code', ''))).zfill(6) == code]
        
        if not stock_records:
            print(f'\n{code}: 未找到')
            continue
        
        r = stock_records[0]
        print(f'\n{code}:')
        
        # 打印关键字段
        key_fields = ['stock_code', 'code', 'short_name', 'name', 'price', 'change_pct', 'change',
                     'volume', 'amount', 'main_net_count', 'cumulative_main_net',
                     'main_net_amount', 'main_behavior', 'is_zt', 'ever_zt']
        
        for field in key_fields:
            if field in r:
                val = r[field]
                print(f'  {field}: {val} (type: {type(val).__name__})')
        
        # 检查change_pct是否为0
        change_pct = r.get('change_pct')
        if change_pct == 0 or change_pct == '0' or change_pct == 0.0:
            print(f'  ⚠️ change_pct 为0!')
        elif change_pct is None:
            print(f'  ⚠️ change_pct 为None!')
    
    # 统计change_pct为0的股票数量
    zero_count = sum(1 for r in records if r.get('change_pct') == 0 or r.get('change_pct') == '0')
    na_count = sum(1 for r in records if r.get('change_pct') is None)
    print(f'\n{"-"*60}')
    print(f'统计: change_pct=0 的股票: {zero_count}, None: {na_count}, 总计: {len(records)}')
