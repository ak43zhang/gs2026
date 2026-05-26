import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'r', encoding='utf-8') as f:
    c = f.read()

old = '''        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={'time_str': time_str})
            if not df.empty:
                df['bond_code'] = df['bond_code'].astype(str)
                result = df.set_index('bond_code')['change_pct'].to_dict()
                # 同时提取价格
                if 'price' in df.columns:
                    price_map = df.set_index('bond_code')['price'].to_dict()
                    for code in result:
                        result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
                return result

        return {}

    except Exception as e:
        print(f"MySQL批量查询债券涨跌幅失败: {e}")'''

new = '''        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={'time_str': time_str})
            if not df.empty:
                df['bond_code'] = df['bond_code'].astype(str)
                result = df.set_index('bond_code')['change_pct'].to_dict()
                # 同时提取价格
                if 'price' in df.columns:
                    price_map = df.set_index('bond_code')['price'].to_dict()
                    for code in result:
                        result[code] = {'change_pct': result[code], 'price': price_map.get(code, '-')}
                else:
                    for code in result:
                        result[code] = {'change_pct': result[code], 'price': '-'}
                return result

        return {}

    except Exception as e:
        print(f"MySQL批量查询债券涨跌幅失败: {e}")'''

if old in c:
    c = c.replace(old, new)
    with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'w', encoding='utf-8') as f:
        f.write(c)
    print('OK: MySQL path fixed')
else:
    print('SKIP: not found')
