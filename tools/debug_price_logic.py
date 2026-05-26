import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util
import pandas as pd

redis_util.init_redis(host='localhost', port=6379, decode_responses=False)

sssj_table = "monitor_zq_sssj_20260518"
redis_key = f"{sssj_table}:10:29:06"

df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
if df is not None:
    print(f"Columns: {list(df.columns)}")
    print(f"'price' in columns: {'price' in df.columns}")
    
    # 模拟 _get_bond_change_pct_batch 的逻辑
    code_col = 'bond_code' if 'bond_code' in df.columns else 'code'
    change_col = 'change_pct'
    
    df[code_col] = df[code_col].astype(str)
    result = df.set_index(code_col)[change_col].to_dict()
    
    print(f"\nResult type: {type(result)}")
    print(f"First value type: {type(list(result.values())[0])}")
    
    # 检查 price 逻辑
    if 'price' in df.columns:
        print("\n'price' in df.columns is TRUE")
        price_map = df.set_index(code_col)['price'].to_dict()
        for code in result:
            result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
        print(f"After price processing, first value type: {type(list(result.values())[0])}")
        print(f"Sample: {list(result.items())[0]}")
    else:
        print("\n'price' in df.columns is FALSE - this is the bug!")
