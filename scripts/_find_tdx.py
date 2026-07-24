import os

results = []
for root, dirs, files in os.walk('.'):
    if any(x in root for x in ['.venv', '.git', 'node_modules']):
        continue
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                    c = fh.read()
                hits = []
                for kw in ['pytdx', 'TdxHq', 'hq_hosts', 'TdxExHq', 'get_security_quotes', 'connect', '服务器', 'tdx']:
                    if kw in c:
                        hits.append(kw)
                if hits and ('tdx' in c.lower() or 'pytdx' in c):
                    results.append((path, hits))
            except:
                pass

with open('tdx_files.txt', 'w', encoding='utf-8') as out:
    for path, hits in results:
        out.write(f"{path}\n    关键词: {hits}\n")
print("OK", len(results))
