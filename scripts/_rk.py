# -*- coding: utf-8 -*-
"""快速TDX测速v2：短超时、限量、防卡死。结果写单值文件。"""
import os, json, time, socket
from datetime import datetime

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)
OUT_JSON = os.path.join(CONFIG_DIR, 'tdx_ips.json')
WS = r'C:\Users\win10_zq\.stepclaw\workspace-main-3'

def w(name, txt):
    try:
        with open(os.path.join(WS, name), 'w', encoding='ascii', errors='ignore') as f:
            f.write(str(txt))
    except: pass

# 立即写一个"开始"标记，证明脚本启动了
w('step.txt', 'STARTED')

try:
    from pytdx.hq import TdxHq_API
    from pytdx.config.hosts import hq_hosts
except Exception as e:
    w('step.txt', 'IMPORT_FAIL')
    w('err.txt', str(e)[:200])
    raise SystemExit

# 候选服务器去重
servers = []
seen = set()
for name, ip, port in hq_hosts:
    k = (ip, int(port))
    if k not in seen:
        seen.add(k)
        servers.append((name, ip, int(port)))

w('step.txt', f'CAND_{len(servers)}')

def tcp_ok(ip, port, t=2):
    try:
        s = socket.create_connection((ip, port), timeout=t); s.close(); return True
    except: return False

usable = []
tcp_pass = 0
tested = 0
for name, ip, port in servers:
    tested += 1
    if tested % 10 == 0:
        w('step.txt', f'TESTED_{tested}/{len(servers)}_tcpok{tcp_pass}_data{len(usable)}')
    if not tcp_ok(ip, port, 2):
        continue
    tcp_pass += 1
    api = TdxHq_API()
    try:
        t0 = time.time()
        if api.connect(ip, port, time_out=3):
            data = api.get_security_bars(8, 1, '600000', 0, 3)
            lat = round((time.time()-t0)*1000)
            if data and len(data) >= 1:
                usable.append({'ip': ip, 'port': port, 'latency_ms': lat, 'name': name})
            api.disconnect()
    except:
        try: api.disconnect()
        except: pass

usable.sort(key=lambda x: x['latency_ms'])
top = usable[:15]

out = {
    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'total_candidates': len(servers),
    'tcp_ok': tcp_pass,
    'data_ok': len(usable),
    'servers': top,
}
with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# 单值结果文件
w('rk_cand.txt', len(servers))
w('rk_tcp.txt', tcp_pass)
w('rk_data.txt', len(usable))
w('rk_best.txt', top[0]['latency_ms'] if top else -1)
w('step.txt', 'FINISHED')
print(f"FINISHED cand={len(servers)} tcp={tcp_pass} data={len(usable)}")
