"""验证TDX连接状态和数据获取"""
import sys
sys.path.insert(0, 'src')

from pytdx.hq import TdxHq_API
import time

SERVERS = [
    ('202.108.253.139', 80),
    ('123.125.108.90', 7709),
    ('218.75.126.9', 7709),
]

# 测试1: 新建连接获取数据
print("=" * 50)
print("测试1: 新建连接")
print("=" * 50)

api = TdxHq_API()
connected = False
for host, port in SERVERS:
    try:
        api.connect(host, port, time_out=3)
        connected = True
        print(f"  连接成功: {host}:{port}")
        break
    except Exception as e:
        print(f"  连接失败: {host}:{port} - {e}")

if not connected:
    print("  所有服务器连接失败!")
    exit(1)

# 测试2: 获取单只债券行情
print("\n测试2: 获取单只行情 (盛德转债 118058)")
try:
    quotes = api.get_security_quotes([(0, '118058')])
    print(f"  返回类型: {type(quotes)}")
    print(f"  返回长度: {len(quotes) if quotes else 'None'}")
    if quotes:
        q = quotes[0]
        print(f"  price(raw): {q.get('price')}")
        print(f"  last_close(raw): {q.get('last_close')}")
        print(f"  open(raw): {q.get('open')}")
        print(f"  vol: {q.get('vol')}")
        print(f"  amount: {q.get('amount')}")
        print(f"  price/100: {q.get('price', 0) / 100}")
    else:
        print("  ⚠️ 返回None!")
except Exception as e:
    print(f"  异常: {e}")

# 测试3: 批量获取(模拟monitor的方式)
print("\n测试3: 批量获取前10只")
try:
    # 获取部分债券代码
    bonds = []
    items = api.get_security_list(0, 0)
    if items:
        for s in items:
            if s['code'].startswith('12'):
                bonds.append((0, s['code']))
                if len(bonds) >= 10:
                    break
    
    print(f"  测试代码: {bonds[:3]}...")
    quotes = api.get_security_quotes(bonds)
    print(f"  返回: {len(quotes) if quotes else 'None'}条")
    if quotes:
        for q in quotes[:3]:
            print(f"    {q['code']}: price={q.get('price')}, vol={q.get('vol')}")
    else:
        print("  ⚠️ 批量获取返回None!")
except Exception as e:
    print(f"  异常: {e}")

# 测试4: 模拟连接复用(等几秒后再查)
print("\n测试4: 等3秒后复用连接")
time.sleep(3)
try:
    quotes = api.get_security_quotes([(0, '118058')])
    if quotes:
        print(f"  复用成功: price={quotes[0].get('price')}")
    else:
        print("  ⚠️ 复用后返回None - 连接可能已断!")
except Exception as e:
    print(f"  复用异常: {e} - 连接已断!")

# 测试5: 检查是否是午休时间导致无数据
print("\n测试5: 当前时间分析")
now = time.strftime('%H:%M:%S')
print(f"  当前时间: {now}")
hour = int(time.strftime('%H'))
minute = int(time.strftime('%M'))
if (hour == 12) or (hour == 11 and minute > 30) or (hour == 12 and minute < 60):
    print("  ⚠️ 当前是午休时间(11:30-13:00), TDX可能不返回实时更新!")
elif hour < 9 or (hour == 9 and minute < 25):
    print("  ⚠️ 未开盘")
elif hour >= 15:
    print("  ⚠️ 已收盘")
else:
    print("  ✅ 交易时段")

api.disconnect()
print("\nDONE")
