"""
测试 get_bond_tdx 数据源
验证：采集效率、完整性、统一结构

使用方法（交易时段）：
    cd F:\pyworkspace2026\gs2026
    .venv\Scripts\python scripts\huatai_trader\test_tdx_source.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

import pandas as pd
from pytdx.hq import TdxHq_API

# 通达信HQ服务器
HQ_SERVERS = [
    ('119.147.212.81', 7709),
    ('114.80.63.12', 7709),
    ('218.75.126.9', 7709),
    ('124.160.88.183', 7709),
    ('106.120.74.86', 7711),
    ('112.95.140.74', 7709),
]


def select_fastest_server():
    """测速选最快服务器"""
    print("[1] 测试HQ服务器延迟...")
    api = TdxHq_API()
    best = None
    best_latency = 9999

    for host, port in HQ_SERVERS:
        try:
            start = time.time()
            with api.connect(host, port, time_out=3):
                api.get_security_count(0)
            latency = (time.time() - start) * 1000
            print(f"    {host}:{port} -> {latency:.0f}ms")
            if latency < best_latency:
                best_latency = latency
                best = (host, port)
        except:
            print(f"    {host}:{port} -> 失败")

    if best:
        print(f"    ✓ 最快: {best[0]}:{best[1]} ({best_latency:.0f}ms)")
    else:
        print("    ✗ 所有服务器连接失败")
    return best


def get_bond_codes_from_tdx(api):
    """从TDX获取全市场可转债代码"""
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

    return bonds


def get_bond_tdx_impl(api, bond_list):
    """
    通过pytdx获取行情并转换为统一结构

    返回 DataFrame 列：
    bond_code, bond_name, price, open, high, low, pre_close, volume, amount, change_pct
    """
    # 批量获取行情（每次最多80只）
    all_quotes = []
    for i in range(0, len(bond_list), 80):
        batch = bond_list[i:i+80]
        params = [(m, c) for m, c, n in batch]
        quotes = api.get_security_quotes(params)
        if quotes:
            all_quotes.extend(quotes)

    # 名称映射
    name_map = {c: n for m, c, n in bond_list}

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

    return pd.DataFrame(rows)


def main():
    print("""
╔══════════════════════════════════════════════════════╗
║        get_bond_tdx 数据源验证测试                  ║
╚══════════════════════════════════════════════════════╝
""")

    # 1. 选服务器
    server = select_fastest_server()
    if not server:
        sys.exit(1)

    host, port = server
    api = TdxHq_API()

    with api.connect(host, port):
        # 2. 获取转债列表
        print(f"\n[2] 获取可转债列表...")
        start = time.time()
        bonds = get_bond_codes_from_tdx(api)
        elapsed = (time.time() - start) * 1000
        sz = sum(1 for m, c, n in bonds if m == 0)
        sh = sum(1 for m, c, n in bonds if m == 1)
        print(f"    深圳:{sz} 上海:{sh} 合计:{len(bonds)} 耗时:{elapsed:.0f}ms")

        # 3. 获取行情并转换
        print(f"\n[3] 获取实时行情...")
        start = time.time()
        df = get_bond_tdx_impl(api, bonds)
        elapsed = (time.time() - start) * 1000
        print(f"    行数: {len(df)}")
        print(f"    耗时: {elapsed:.0f}ms")

        # 4. 验证统一结构
        print(f"\n[4] 验证统一结构...")
        expected_cols = ['bond_code', 'bond_name', 'price', 'open', 'high',
                         'low', 'pre_close', 'volume', 'amount', 'change_pct']
        actual_cols = list(df.columns)
        missing = [c for c in expected_cols if c not in actual_cols]
        if missing:
            print(f"    ✗ 缺少列: {missing}")
        else:
            print(f"    ✓ 列完整: {actual_cols}")

        # 5. 数据完整性
        print(f"\n[5] 数据完整性...")
        active = df[df['price'] > 0]
        print(f"    有效数据(price>0): {len(active)}/{len(df)}")
        print(f"    dtypes:")
        for col in expected_cols:
            print(f"      {col}: {df[col].dtype}")

        # 6. 样本数据
        if len(active) > 0:
            print(f"\n[6] 样本数据 (成交额Top5):")
            top = active.nlargest(5, 'amount')
            for _, r in top.iterrows():
                print(f"    {r['bond_code']} {r['bond_name']:<6} "
                      f"价:{r['price']:.2f} 涨:{r['change_pct']:+.2f}% "
                      f"额:{r['amount']/10000:.0f}万")

        # 7. 稳定性测试
        print(f"\n[7] 稳定性测试 (连续10次, 间隔3秒)...")
        times = []
        for i in range(10):
            start = time.time()
            df_tick = get_bond_tdx_impl(api, bonds)
            elapsed = (time.time() - start) * 1000
            valid = len(df_tick[df_tick['price'] > 0])
            times.append(elapsed)
            print(f"    第{i+1:2d}次: {elapsed:5.0f}ms  有效:{valid}只")
            if i < 9:
                time.sleep(3)

        print(f"\n    统计: 平均{sum(times)/len(times):.0f}ms "
              f"最小{min(times):.0f}ms 最大{max(times):.0f}ms")

    # 结论
    print(f"\n{'='*55}")
    if times and max(times) < 2000 and len(active) >= 400:
        print("  ✓ 测试通过！get_bond_tdx 可用。")
    else:
        print("  ⚠ 需关注：数据量或延迟不达标。")
    print(f"{'='*55}")


if __name__ == '__main__':
    main()
