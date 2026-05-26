import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

# 完全模拟 _get_bond_change_pct_batch 的逻辑
from gs2026.utils import redis_util
import pandas as pd

redis_util.init_redis(host='localhost', port=6379, decode_responses=False)

sssj_table = "monitor_zq_sssj_20260518"
time_str = "10:29:06"
redis_key = f"{sssj_table}:{time_str}"

df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)

print(f"df is not None: {df is not None}")
print(f"df.empty: {df.empty if df is not None else 'N/A'}")

if df is not None and not df.empty:
    print(f"Columns: {repr(list(df.columns))}")
    
    # 检查 price 列
    has_price = 'price' in df.columns
    print(f"'price' in df.columns: {has_price}")
    
    # 如果 has_price 为 False，检查原因
    if not has_price:
        print(f"All columns: {list(df.columns)}")
        for c in df.columns:
            print(f"  Column: {repr(c)}, equals 'price': {c == 'price'}")
    else:
        print("Price column found!")
        code_col = 'bond_code' if 'bond_code' in df.columns else 'code'
        change_col = 'change_pct'
        
        df[code_col] = df[code_col].astype(str)
        result = df.set_index(code_col)[change_col].to_dict()
        
        price_map = df.set_index(code_col)['price'].to_dict()
        for code in result:
            result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
        
        print(f"Sample result: {list(result.items())[0]}")
