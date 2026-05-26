import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 找到第一个函数中的 if df is not None and not df.empty:
old = '''        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)

        if df is not None and not df.empty:
            # 构建字典 {bond_code: change_pct}
            code_col = 'bond_code' if 'bond_code' in df.columns else 'code'
            change_col = 'change_pct'

            df[code_col] = df[code_col].astype(str)
            result = df.set_index(code_col)[change_col].to_dict()
            
            # 同时提取价格字段
            if 'price' in df.columns:
                price_map = df.set_index(code_col)['price'].to_dict()
                for code in result:
                    result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
            
            return result'''

new = '''        df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)

        # 如果指定时间不存在，尝试查找最近的时间
        if df is None or df.empty:
            available_time = _get_latest_sssj_time(date, 'bond')
            if available_time:
                redis_key = f"{sssj_table}:{available_time}"
                df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)

        if df is not None and not df.empty:
            # 构建字典 {bond_code: change_pct}
            code_col = 'bond_code' if 'bond_code' in df.columns else 'code'
            change_col = 'change_pct'

            df[code_col] = df[code_col].astype(str)
            result = df.set_index(code_col)[change_col].to_dict()
            
            # 同时提取价格字段
            if 'price' in df.columns:
                price_map = df.set_index(code_col)['price'].to_dict()
                for code in result:
                    result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
            
            return result'''

if old in c:
    c = c.replace(old, new)
    with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'w', encoding='utf-8') as f:
        f.write(c)
    print('OK: Added fallback time logic')
else:
    print('SKIP: Pattern not found')
