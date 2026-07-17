"""
测试 get_bond_tdx 数据源
验证：采集效率、完整性、统一结构、价格精度

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
    ('218.75.126.9', 7709),
    ('202.108.253.131', 7709),
    ('202.108.253.139', 80),
    ('123.125.108.90', 7709)
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
    
    关键：TDX返回的价格类字段需要除以100（原始值是实际值的100倍）
    
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

    # 转换为统一结构（价格类字段除以100）
    rows = []
    for q in all_quotes:
        code = q.get('code', '')
        # TDX价格字段需要除以100
        price = q.get('price', 0) / 100
        pre_close = q.get('last_close', 0) / 100
        open_price = q.get('open', 0) / 100
        high = q.get('high', 0) / 100
        low = q.get('low', 0) / 100

        change_pct = 0
        if pre_close and pre_close > 0:
            change_pct = (price - pre_close) / pre_close * 100

        rows.append({
            'bond_code': code,
            'bond_name': name_map.get(code, ''),
            'price': price,
            'open': open_price,
            'high': high,
            'low': low,
            'pre_close': pre_close,
            'volume': q.get('vol', 0),
            'amount': q.get('amount', 0),
            'change_pct': round(change_pct, 4),
        })

    return pd.DataFrame(rows)


def test_price_realtime(api, bonds, test_code='123257', rounds=10, interval=3):
    """
    测试价格实时性：连续获取多次，观察价格是否变化
    
    验证：get_security_quotes 返回的是实时快照，应该每3秒有变化
    """
    print(f"\n[8] 价格实时性测试 (连续{rounds}次, 间隔{interval}秒)...")
    print(f"    测试标的: {test_code}")
    print(f"    {'轮次':<6} {'时间':<10} {'价格':>10} {'涨跌%':>8} {'成交量':>12}")
    print(f"    {'-'*50}")
    
    prices = []
    for i in range(rounds):
        # 获取全市场行情
        df = get_bond_tdx_impl(api, bonds)
        
        # 查找测试标的
        row = df[df['bond_code'] == test_code]
        if not row.empty:
            r = row.iloc[0]
            prices.append(r['price'])
            print(f"    {i+1:<6} {time.strftime('%H:%M:%S'):<10} {r['price']:>10.3f} {r['change_pct']:>+8.2f} {r['volume']:>12.0f}")
        else:
            print(f"    {i+1:<6} {time.strftime('%H:%M:%S'):<10} {'未找到':>10}")
        
        if i < rounds - 1:
            time.sleep(interval)
    
    # 分析价格变化
    unique_prices = len(set(round(p, 3) for p in prices))
    print(f"\n    统计: 共{len(prices)}次采样, {unique_prices}个不同价格")
    if unique_prices > 1:
        print(f"    ✓ 价格有变化，实时性正常")
    else:
        print(f"    ⚠ 价格无变化，可能为收盘时段或数据未更新")
    
    return prices


def test_connection_stability(api, bonds, duration=300, interval=30):
    """
    测试长连接稳定性
    
    保持连接，每interval秒查询一次，看连接是否仍然有效
    用于验证是否可以实施"只连接一次"的连接池方案
    
    Args:
        api: 已连接的TdxHq_API实例
        bonds: 债券列表
        duration: 测试总时长（秒）
        interval: 查询间隔（秒）
    """
    print(f"    测试时长: {duration}秒, 间隔: {interval}秒")
    print(f"    {'次数':<6} {'时间':<10} {'状态':<10} {'延迟(ms)':>10} {'有效数据':>10}")
    print(f"    {'-'*50}")
    
    rounds = duration // interval
    success_count = 0
    fail_count = 0
    
    for i in range(rounds):
        start = time.time()
        try:
            # 获取行情
            df = get_bond_tdx_impl(api, bonds)
            elapsed = (time.time() - start) * 1000
            valid = len(df[df['price'] > 0])
            
            if valid > 0:
                success_count += 1
                status = "✓ 正常"
            else:
                fail_count += 1
                status = "✗ 无数据"
            
            print(f"    {i+1:<6} {time.strftime('%H:%M:%S'):<10} {status:<10} {elapsed:>10.0f} {valid:>10}只")
            
        except Exception as e:
            fail_count += 1
            elapsed = (time.time() - start) * 1000
            print(f"    {i+1:<6} {time.strftime('%H:%M:%S'):<10} {'✗ 异常':<10} {elapsed:>10.0f} {str(e)[:20]:>10}")
        
        if i < rounds - 1:
            time.sleep(interval)
    
    # 结论
    print(f"\n    统计: 成功{success_count}/{rounds}次, 失败{fail_count}次")
    if fail_count == 0:
        print(f"    ✓ 长连接稳定，可以实施连接池方案（只连接一次）")
    elif fail_count <= 2:
        print(f"    △ 长连接基本稳定，建议实施连接池+自动重连")
    else:
        print(f"    ✗ 长连接不稳定，建议保持每次新建连接")
    
    return fail_count == 0


def main():
    print("""
╔══════════════════════════════════════════════════════╗
║        get_bond_tdx 数据源验证测试 (v2.0)           ║
║        修复：价格精度（除以100）                     ║
║        新增：实时性验证                              ║
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

        # 5. 价格精度验证
        print(f"\n[5] 价格精度验证...")
        active = df[df['price'] > 0]
        if len(active) > 0:
            sample = active.head(5)
            print(f"    样本价格（应接近100左右，而非10000）:")
            for _, r in sample.iterrows():
                print(f"      {r['bond_code']}: 价={r['price']:.3f}, 开={r['open']:.3f}, 高={r['high']:.3f}, 低={r['low']:.3f}, 昨收={r['pre_close']:.3f}")
            
            # 检查价格是否合理（可转债通常在80-150之间）
            avg_price = active['price'].mean()
            if 50 < avg_price < 200:
                print(f"    ✓ 价格范围正常（平均{avg_price:.2f}）")
            else:
                print(f"    ✗ 价格异常（平均{avg_price:.2f}），可能未除以100")

        # 6. 数据完整性
        print(f"\n[6] 数据完整性...")
        print(f"    有效数据(price>0): {len(active)}/{len(df)}")
        print(f"    dtypes:")
        for col in expected_cols:
            print(f"      {col}: {df[col].dtype}")

        # 7. 样本数据
        if len(active) > 0:
            print(f"\n[7] 样本数据 (成交额Top5):")
            top = active.nlargest(5, 'amount')
            for _, r in top.iterrows():
                print(f"    {r['bond_code']} {r['bond_name']:<6} "
                      f"价:{r['price']:.2f} 涨:{r['change_pct']:+.2f}% "
                      f"额:{r['amount']/10000:.0f}万")

        # 8. 稳定性测试
        print(f"\n[8] 稳定性测试 (连续10次, 间隔3秒)...")
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

        # 9. 价格实时性测试（交易时段才有效）
        # 找一只活跃的债进行测试
        if len(active) > 0:
            # 选成交额最大的一只
            test_code = active.nlargest(1, 'amount').iloc[0]['bond_code']
            test_price_realtime(api, bonds, test_code=test_code, rounds=10, interval=3)

        # 10. 长连接稳定性测试
        print(f"\n[10] 长连接稳定性测试...")
        test_connection_stability(api, bonds, duration=300, interval=30)

    # 结论
    print(f"\n{'='*55}")
    if times and max(times) < 2000 and len(active) >= 400:
        print("  ✓ 测试通过！get_bond_tdx 可用。")
    else:
        print("  ⚠ 需关注：数据量或延迟不达标。")
    print(f"{'='*55}")


if __name__ == '__main__':
    main()
