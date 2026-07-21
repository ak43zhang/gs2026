"""测试所有TDX服务器，找到能返回数据的"""
import sys
sys.path.insert(0, 'src')
from pytdx.hq import TdxHq_API

SERVERS = [
    ('202.108.253.139', 80),
    ('123.125.108.90', 7709),
    ('218.75.126.9', 7709),
    ('202.108.253.131', 7709),
    ('115.238.56.198', 7709),
    ('221.231.141.60', 7709),
    ('59.173.18.140', 7709),
    ('180.153.18.170', 7709),
    ('47.103.48.45', 7709),
]

print("逐个测试TDX服务器...")
print()

for host, port in SERVERS:
    api = TdxHq_API()
    try:
        api.connect(host, port, time_out=3)
        # 测试实际查询
        quotes = api.get_security_quotes([(0, '128141')])
        if quotes and len(quotes) > 0 and quotes[0].get('price', 0) > 0:
            print(f"  ✅ {host}:{port} - 数据正常! price={quotes[0]['price']}")
        else:
            print(f"  ❌ {host}:{port} - 连接成功但无数据 (quotes={quotes})")
        api.disconnect()
    except Exception as e:
        print(f"  ❌ {host}:{port} - 连接失败: {e}")
