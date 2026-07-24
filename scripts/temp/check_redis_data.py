import pandas as pd
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util

sssj_table = 'monitor_gp_sssj_20250626'
codes = ['688596', '688300', '600481']  # 正帆科技、联瑞新材、双良节能

for time_str in ['10:00:15', '10:00:18']:
    print(f'\n=== {time_str} ===')
    redis_key = f'{sssj_table}:{time_str}'
    df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
    
    if df is not None and not df.empty:
        # 检查列名
        print(f'列名: {list(df.columns)}')
        
        # 查找指定股票
        for code in codes:
            code_col = 'stock_code' if 'stock_code' in df.columns else 'code'
            mask = df[code_col].astype(str).str.zfill(6) == code
            row = df[mask]
            if not row.empty:
                change_pct_val = row['change_pct'].values[0] if 'change_pct' in row.columns else 'N/A'
                change_val = row['change'].values[0] if 'change' in row.columns else 'N/A'
                main_net_count = row['main_net_count'].values[0] if 'main_net_count' in row.columns else 'N/A'
                print(f'{code}: change_pct={change_pct_val}, change={change_val}, main_net_count={main_net_count}')
            else:
                print(f'{code}: 未找到')
    else:
        print('数据为空或不存在')
