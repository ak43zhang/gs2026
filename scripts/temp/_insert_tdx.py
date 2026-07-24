"""Insert get_bond_tdx into monitor_bond.py"""
import re

path = 'src/gs2026/monitor/monitor_bond.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Already exists?
if 'def get_bond_tdx' in content:
    print('get_bond_tdx already exists, skipping')
    exit(0)

# The get_bond_tdx function code
tdx_func = '''
def get_bond_tdx():
    """通过pytdx获取可转债实时行情，转换为统一结构"""
    try:
        from pytdx.hq import TdxHq_API

        tdx_servers = [
            ('119.147.212.81', 7709),
            ('114.80.63.12', 7709),
            ('218.75.126.9', 7709),
            ('124.160.88.183', 7709),
            ('106.120.74.86', 7711),
        ]

        api = TdxHq_API()
        connected = False
        for host, port in tdx_servers:
            try:
                api.connect(host, port, time_out=3)
                connected = True
                break
            except:
                continue

        if not connected:
            logger.warning("[tdx] 所有HQ服务器连接失败")
            return pd.DataFrame()

        try:
            # 获取可转债代码列表
            bonds = []
            # 深圳 (market=0): 12开头
            count = api.get_security_count(0)
            for start in range(0, count, 1000):
                items = api.get_security_list(0, start)
                if items:
                    for s in items:
                        if s['code'].startswith('12'):
                            bonds.append((0, s['code'], s.get('name', '')))
            # 上海 (market=1): 11开头
            count = api.get_security_count(1)
            for start in range(0, count, 1000):
                items = api.get_security_list(1, start)
                if items:
                    for s in items:
                        if s['code'].startswith('11'):
                            bonds.append((1, s['code'], s.get('name', '')))

            # 批量获取行情（每次80只）
            all_quotes = []
            for i in range(0, len(bonds), 80):
                batch = bonds[i:i+80]
                params = [(m, c) for m, c, n in batch]
                quotes = api.get_security_quotes(params)
                if quotes:
                    all_quotes.extend(quotes)

            # 名称映射
            name_map = {c: n for m, c, n in bonds}

            # 转换为统一结构
            rows = []
            for q in all_quotes:
                code = q.get('code', '')
                price = q.get('price', 0)
                pre_close = q.get('last_close', 0)
                change_pct = 0
                if pre_close and pre_close > 0:
                    change_pct = (price - pre_close) / pre_close * 100

                rows.append({
                    'bond_code': code,
                    'bond_name': name_map.get(code, ''),
                    'price': price,
                    'open': q.get('open', 0),
                    'high': q.get('high', 0),
                    'low': q.get('low', 0),
                    'pre_close': pre_close,
                    'volume': q.get('vol', 0),
                    'amount': q.get('amount', 0),
                    'change_pct': round(change_pct, 4),
                })

            df = pd.DataFrame(rows)
            logger.info(f"[tdx] 获取{len(df)}只转债行情")
            return df

        finally:
            api.disconnect()

    except Exception as e:
        logger.error(f"[tdx] 获取行情失败: {e}")
        return pd.DataFrame()

'''

# Find handlers dict and insert function before it, add 'tdx' entry
# Match the handlers = { line
match = re.search(r'^(\s*)(handlers\s*=\s*\{[^}]+\})', content, re.MULTILINE | re.DOTALL)
if not match:
    print("ERROR: handlers dict not found!")
    exit(1)

indent = match.group(1)
handlers_text = match.group(2)
print(f"Found handlers at indent=[{repr(indent)}]")

# Indent the function to match
indented_func = ''
for line in tdx_func.strip().split('\n'):
    indented_func += indent + line + '\n'
indented_func += '\n'

# Add 'tdx': get_bond_tdx to handlers dict
if "'tdx'" not in handlers_text:
    handlers_text = handlers_text.rstrip('}').rstrip() + "\n" + indent + "    'tdx': get_bond_tdx,\n" + indent + "}"

# Replace in content
new_content = content[:match.start()] + indented_func + indent + handlers_text + content[match.end():]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

# Verify
with open(path, 'r', encoding='utf-8') as f:
    verify = f.read()

print(f"get_bond_tdx exists: {'def get_bond_tdx' in verify}")
print(f"'tdx' in handlers: {\"'tdx'\" in verify}")
print("DONE")
