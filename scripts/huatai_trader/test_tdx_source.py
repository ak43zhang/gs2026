"""
pytdx 通达信数据源测试脚本
用于验证数据可用性和稳定性

使用方法（交易时段运行）：
    cd F:\pyworkspace2026\gs2026
    .venv\Scripts\python scripts\huatai_trader\test_tdx_source.py

测试内容：
1. 连接TDX HQ服务器（自动选最快）
2. 获取全市场可转债实时行情
3. 验证数据完整性
4. 模拟Min1BarBuilder计算
5. 连续运行稳定性测试
"""

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

import pandas as pd
from pytdx.hq import TdxHq_API

# ==================== 配置 ====================

# 通达信HQ服务器列表
HQ_SERVERS = [
    ('119.147.212.81', 7709),
    ('114.80.63.12', 7709),
    ('218.75.126.9', 7709),
    ('124.160.88.183', 7709),
    ('106.120.74.86', 7711),
    ('112.95.140.74', 7709),
    ('113.105.142.162', 7709),
    ('119.147.171.206', 443),
    ('121.14.110.194', 443),
    ('60.28.23.80', 7709),
]

# 可转债代码前缀（用于过滤）
# 深圳: 12xxxx (market=0)
# 上海: 11xxxx (market=1)
BOND_PREFIXES_SZ = ('12',)  # 深圳转债
BOND_PREFIXES_SH = ('11',)  # 上海转债


# ==================== 工具函数 ====================

def test_server_speed(servers, timeout=3):
    """测试服务器延迟，返回最快的"""
    print("\n[1] 测试HQ服务器延迟...")
    results = []
    api = TdxHq_API()
    
    for host, port in servers:
        try:
            start = time.time()
            with api.connect(host, port, time_out=timeout):
                # 简单请求测试延迟
                api.get_security_count(0)
            latency = (time.time() - start) * 1000
            results.append((host, port, latency))
            print(f"    {host}:{port} -> {latency:.0f}ms")
        except Exception as e:
            print(f"    {host}:{port} -> 超时/失败")
    
    if not results:
        print("    ✗ 所有服务器连接失败！")
        return None, None
    
    # 选最快的
    results.sort(key=lambda x: x[2])
    best = results[0]
    print(f"    ✓ 最快: {best[0]}:{best[1]} ({best[2]:.0f}ms)")
    return best[0], best[1]


def get_bond_codes(api):
    """获取全市场可转债代码列表"""
    bonds = []
    
    # 深圳市场 (market=0)
    count = api.get_security_count(0)
    for start in range(0, count, 1000):
        stocks = api.get_security_list(0, start)
        if stocks:
            for s in stocks:
                code = s['code']
                if code.startswith(BOND_PREFIXES_SZ):
                    bonds.append((0, code, s.get('name', '')))
    
    # 上海市场 (market=1)
    count = api.get_security_count(1)
    for start in range(0, count, 1000):
        stocks = api.get_security_list(1, start)
        if stocks:
            for s in stocks:
                code = s['code']
                if code.startswith(BOND_PREFIXES_SH):
                    bonds.append((1, code, s.get('name', '')))
    
    return bonds


def get_quotes_batch(api, bond_list):
    """批量获取实时行情（每次最多80只）"""
    all_quotes = []
    batch_size = 80
    
    for i in range(0, len(bond_list), batch_size):
        batch = bond_list[i:i + batch_size]
        params = [(market, code) for market, code, name in batch]
        quotes = api.get_security_quotes(params)
        if quotes:
            all_quotes.extend(quotes)
    
    return all_quotes


def build_dataframe(quotes, bond_names):
    """将行情数据构建为DataFrame"""
    rows = []
    for q in quotes:
        code = q.get('code', '')
        name = bond_names.get(code, '')
        price = q.get('price', 0)
        pre_close = q.get('last_close', 0)
        
        # 计算涨跌幅
        change_pct = 0
        if pre_close and pre_close > 0:
            change_pct = (price - pre_close) / pre_close * 100
        
        rows.append({
            'bond_code': code,
            'bond_name': name,
            'price': price,
            'open': q.get('open', 0),
            'high': q.get('high', 0),
            'low': q.get('low', 0),
            'pre_close': pre_close,
            'volume': q.get('vol', 0),
            'amount': q.get('amount', 0),
            'change_pct': round(change_pct, 4),
            'bid1': q.get('bid1', 0),
            'ask1': q.get('ask1', 0),
            'bid_vol1': q.get('bid_vol1', 0),
            'ask_vol1': q.get('ask_vol1', 0),
        })
    
    df = pd.DataFrame(rows)
    
    # 成交额排名
    if len(df) > 0 and 'amount' in df.columns:
        df['amount_rank'] = df['amount'].rank(ascending=False, method='min').astype(int)
    
    return df


# ==================== Min1BarBuilder ====================

class Min1BarBuilder:
    """固定分钟边界的1分钟K线构建器"""
    
    def __init__(self):
        self._bars = {}
    
    def update_all(self, df, timestamp):
        """批量更新所有债的bar"""
        minute_key = timestamp.strftime('%H:%M')
        
        for _, row in df.iterrows():
            code = row['bond_code']
            price = row['price']
            total_amount = row['amount']
            
            if price <= 0:
                continue
            
            state = self._bars.get(code)
            if state is None:
                self._bars[code] = {
                    'current_minute': minute_key,
                    'current_bar': {
                        'open': price, 'high': price, 'low': price, 'close': price,
                        'amount_start': total_amount, 'amount_end': total_amount,
                    },
                    'prev_bar': None,
                    'prev_prev_bar': None,
                }
                continue
            
            state = self._bars[code]
            
            if minute_key != state['current_minute']:
                # 分钟切换
                state['prev_prev_bar'] = state['prev_bar']
                state['prev_bar'] = state['current_bar']
                state['current_bar'] = {
                    'open': price, 'high': price, 'low': price, 'close': price,
                    'amount_start': total_amount, 'amount_end': total_amount,
                }
                state['current_minute'] = minute_key
            else:
                # 同分钟内更新
                bar = state['current_bar']
                bar['high'] = max(bar['high'], price)
                bar['low'] = min(bar['low'], price)
                bar['close'] = price
                bar['amount_end'] = total_amount
    
    def get_min1_metrics(self, code):
        """获取上一根完整bar的指标"""
        state = self._bars.get(code)
        if not state or not state['prev_bar']:
            return 0, 0, 0  # min1_change_pct, min1_amount, is_body_up
        
        prev = state['prev_bar']
        prev_prev = state['prev_prev_bar']
        
        min1_amount = prev['amount_end'] - prev['amount_start']
        
        if prev_prev and prev_prev['close'] > 0:
            min1_change_pct = (prev['close'] - prev_prev['close']) / prev_prev['close'] * 100
        else:
            min1_change_pct = 0
        
        is_body_up = 1 if prev['close'] > prev['open'] else 0
        
        return round(min1_change_pct, 4), round(min1_amount, 2), is_body_up
    
    def enrich_df(self, df):
        """为DataFrame添加min1指标列"""
        min1_data = []
        for _, row in df.iterrows():
            pct, amt, up = self.get_min1_metrics(row['bond_code'])
            min1_data.append({'min1_change_pct': pct, 'min1_amount': amt, 'is_body_up': up})
        
        min1_df = pd.DataFrame(min1_data)
        return pd.concat([df.reset_index(drop=True), min1_df], axis=1)


# ==================== 主测试流程 ====================

def main():
    print("""
╔══════════════════════════════════════════════════════╗
║       pytdx 通达信数据源 - 可用性验证测试           ║
╚══════════════════════════════════════════════════════╝
""")
    
    # 1. 测速选服务器
    host, port = test_server_speed(HQ_SERVERS)
    if not host:
        print("\n无法连接任何HQ服务器，请检查网络。")
        sys.exit(1)
    
    # 2. 连接并获取转债列表
    api = TdxHq_API()
    with api.connect(host, port):
        print(f"\n[2] 获取可转债列表...")
        start = time.time()
        bonds = get_bond_codes(api)
        elapsed = (time.time() - start) * 1000
        
        # 按市场分类
        sz_count = sum(1 for m, c, n in bonds if m == 0)
        sh_count = sum(1 for m, c, n in bonds if m == 1)
        print(f"    深圳: {sz_count}只  上海: {sh_count}只  合计: {len(bonds)}只")
        print(f"    耗时: {elapsed:.0f}ms")
        
        # 名称映射
        bond_names = {code: name for market, code, name in bonds}
        
        # 3. 获取实时行情
        print(f"\n[3] 获取实时行情...")
        start = time.time()
        quotes = get_quotes_batch(api, bonds)
        elapsed = (time.time() - start) * 1000
        print(f"    获取到: {len(quotes)}只  耗时: {elapsed:.0f}ms")
        
        # 构建DataFrame
        df = build_dataframe(quotes, bond_names)
        
        # 过滤无效数据（价格为0的通常是已退市或停牌）
        active = df[df['price'] > 0]
        print(f"    有效(price>0): {len(active)}只")
        
        # 显示样本
        if len(active) > 0:
            print(f"\n    样本数据(成交额Top5):")
            top5 = active.nlargest(5, 'amount')
            for _, row in top5.iterrows():
                print(f"      {row['bond_code']} {row['bond_name']:<6} "
                      f"价:{row['price']:.2f} 涨:{row['change_pct']:+.2f}% "
                      f"额:{row['amount']/10000:.0f}万 "
                      f"排名:{row['amount_rank']}")
        
        # 4. Min1BarBuilder 测试
        print(f"\n[4] Min1BarBuilder 模拟测试...")
        builder = Min1BarBuilder()
        now = datetime.now()
        builder.update_all(active, now)
        enriched = builder.enrich_df(active)
        print(f"    列: {list(enriched.columns)}")
        print(f"    行数: {len(enriched)}")
        print(f"    (注: 首次运行min1指标为0，需要至少2分钟数据才有值)")
        
        # 5. 稳定性测试
        print(f"\n[5] 稳定性测试 (连续10轮, 间隔3秒)...")
        times = []
        errors = 0
        
        for i in range(10):
            try:
                start = time.time()
                quotes = get_quotes_batch(api, bonds)
                elapsed = (time.time() - start) * 1000
                times.append(elapsed)
                
                valid = sum(1 for q in quotes if q.get('price', 0) > 0)
                print(f"    轮次{i+1:2d}: {elapsed:6.0f}ms  有效:{valid}只", end='')
                
                if i > 0:
                    # 更新bar
                    df_tick = build_dataframe(quotes, bond_names)
                    builder.update_all(df_tick[df_tick['price'] > 0], datetime.now())
                
                print()
            except Exception as e:
                errors += 1
                print(f"    轮次{i+1:2d}: 错误 - {e}")
            
            if i < 9:
                time.sleep(3)
        
        # 统计
        if times:
            print(f"\n    统计:")
            print(f"      平均耗时: {sum(times)/len(times):.0f}ms")
            print(f"      最小: {min(times):.0f}ms  最大: {max(times):.0f}ms")
            print(f"      错误次数: {errors}")
            print(f"      成功率: {(10-errors)/10*100:.0f}%")
    
    # 最终结论
    print(f"\n{'=' * 55}")
    if times and len(times) >= 8 and max(times) < 3000:
        print("  ✓ 测试通过！pytdx数据源可用，满足3秒tick需求。")
    elif times:
        print("  ⚠ 部分通过，但延迟或稳定性需关注。")
    else:
        print("  ✗ 测试失败，请检查网络连接。")
    print(f"{'=' * 55}")


if __name__ == '__main__':
    main()
