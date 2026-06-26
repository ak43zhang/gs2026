#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从Redis获取指定时间点的股票数据，用于排查change_pct异常问题
"""
import sys
import json
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
from gs2026.utils import redis_util
from gs2026.utils.config_util import cfg

# 初始化Redis连接
redis_util.init_redis(cfg)

def analyze_stock_data():
    sssj_table = 'monitor_gp_sssj_20250626'
    codes = ['688596', '688300', '600481']  # 正帆科技、联瑞新材、双良节能
    
    for time_str in ['10:00:15', '10:00:18']:
        print(f'\n{"="*60}')
        print(f'时间: {time_str}')
        print(f'{"="*60}')
        
        redis_key = f'{sssj_table}:{time_str}'
        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
        
        if df is None or df.empty:
            print('数据为空或不存在')
            continue
        
        # 检查列名
        print(f'\n所有列名: {list(df.columns)}')
        
        # 检查change_pct相关列
        change_cols = [c for c in df.columns if 'change' in c.lower()]
        print(f'\nchange相关列: {change_cols}')
        
        # 查找指定股票
        code_col = 'stock_code' if 'stock_code' in df.columns else 'code'
        
        print(f'\n{"-"*60}')
        print(f'股票详情:')
        print(f'{"-"*60}')
        
        for code in codes:
            mask = df[code_col].astype(str).str.zfill(6) == code
            row = df[mask]
            
            if row.empty:
                print(f'\n{code}: 未找到')
                continue
            
            print(f'\n{code}:')
            
            # 打印关键字段
            key_fields = ['stock_code', 'short_name', 'price', 'change_pct', 'change',
                         'volume', 'amount', 'main_net_count', 'cumulative_main_net',
                         'main_net_amount', 'main_behavior']
            
            for field in key_fields:
                if field in row.columns:
                    val = row[field].values[0]
                    print(f'  {field}: {val} (type: {type(val).__name__})')
                else:
                    print(f'  {field}: 列不存在')
        
        # 统计change_pct为0的股票数量
        if 'change_pct' in df.columns:
            zero_count = (df['change_pct'] == 0).sum()
            na_count = df['change_pct'].isna().sum()
            print(f'\n{"-"*60}')
            print(f'统计: change_pct=0 的股票: {zero_count}, NaN: {na_count}, 总计: {len(df)}')

if __name__ == '__main__':
    analyze_stock_data()
