import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 回退 Redis 路径的 else 分支
old_redis = '''            df[code_col] = df[code_col].astype(str)
            result = df.set_index(code_col)[change_col].to_dict()
            
            # 同时提取价格字段（如果有）
            if 'price' in df.columns:
                price_map = df.set_index(code_col)['price'].to_dict()
                for code in result:
                    result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
            else:
                # 没有价格字段，包装成统一格式
                for code in result:
                    result[code] = {'change_pct': result[code], 'price': '-'}
            
            return result'''

new_redis = '''            df[code_col] = df[code_col].astype(str)
            result = df.set_index(code_col)[change_col].to_dict()
            
            # 同时提取价格字段
            if 'price' in df.columns:
                price_map = df.set_index(code_col)['price'].to_dict()
                for code in result:
                    result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
            
            return result'''

c = c.replace(old_redis, new_redis)

# 回退 MySQL 路径的 else 分支
old_mysql = '''                # 同时提取价格
                if 'price' in df.columns:
                    price_map = df.set_index('bond_code')['price'].to_dict()
                    for code in result:
                        result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
                else:
                    for code in result:
                        result[code] = {'change_pct': result[code], 'price': '-'}
                return result'''

new_mysql = '''                # 同时提取价格
                if 'price' in df.columns:
                    price_map = df.set_index('bond_code')['price'].to_dict()
                    for code in result:
                        result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
                return result'''

c = c.replace(old_mysql, new_mysql)

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'w', encoding='utf-8') as f:
    f.write(c)
print('OK: rolled back')
