# -*- coding: utf-8 -*-
"""
TDX 行情服务器测速与刷新脚本（第一步：纯测速，零侵入）

功能：
1. 测速 pytdx 内置的全部行情服务器（标准市场 hq_hosts，几十个）
2. 对每个服务器：TCP连通 → pytdx连接 → 实测拉取债券/股票数据 → 记录延迟
3. 筛选出「能真正拉到数据」且延迟最低的服务器
4. 输出可用IP列表到 config/tdx_ips.json（供后续第二步接入）

用法：
    python scripts/refresh_tdx_ips.py

输出：
    config/tdx_ips.json           可用IP列表（按延迟升序）
    刷新结果摘要打印到控制台
"""
import os
import json
import time
import socket
from datetime import datetime

# 结果目录
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'configs')
os.makedirs(CONFIG_DIR, exist_ok=True)
OUT_JSON = os.path.join(CONFIG_DIR, 'tdx_ips.json')

# 测试用标的（浦发银行，全市场都有；债券可用后续替换）
TEST_SYMBOL = '600000'
TEST_MARKET = 1   # 1=上海
TEST_CATEGORY = 8 # 8=1分钟K线
MIN_BARS = 1      # 至少拉到1条才算可用

# 连接与拉数据的超时（秒）
CONNECT_TIMEOUT = 4
TCP_TIMEOUT = 3


def get_candidate_servers():
    """获取候选服务器列表：pytdx内置 + 代码中已提取的IP"""
    servers = []
    seen = set()

    # 1. pytdx 内置服务器
    try:
        from pytdx.config.hosts import hq_hosts
        for name, ip, port in hq_hosts:
            key = (ip, port)
            if key not in seen:
                seen.add(key)
                servers.append({'name': name, 'ip': ip, 'port': int(port)})
    except Exception as e:
        print(f"[警告] 读取pytdx内置服务器失败: {e}")

    # 2. 代码中已提取的IP（_pool_ips.txt，如果存在）
    pool_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '_pool_ips.txt')
    if os.path.exists(pool_file):
        with open(pool_file, 'r', encoding='ascii', errors='ignore') as f:
            for line in f:
                ip = line.strip()
                if ip and ip.count('.') == 3:
                    for port in (7709, 7721):
                        key = (ip, port)
                        if key not in seen:
                            seen.add(key)
                            servers.append({'name': f'pool_{ip}', 'ip': ip, 'port': port})

    return servers


def tcp_check(ip, port, timeout=TCP_TIMEOUT):
    """TCP连通性检查"""
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def test_server(api_cls, srv):
    """
    测试单个服务器：连接 + 实测拉数据 + 计时
    返回 dict(ip, port, name, tcp, data_bars, latency_ms, ok)
    """
    ip, port = srv['ip'], srv['port']
    result = {'ip': ip, 'port': port, 'name': srv['name'],
              'tcp': False, 'data_bars': 0, 'latency_ms': None, 'ok': False}

    # TCP先探
    if not tcp_check(ip, port):
        return result
    result['tcp'] = True

    # pytdx连接 + 拉数据 + 计时
    api = api_cls()
    try:
        t0 = time.time()
        if api.connect(ip, port, time_out=CONNECT_TIMEOUT):
            data = api.get_security_bars(TEST_CATEGORY, TEST_MARKET, TEST_SYMBOL, 0, 5)
            latency = round((time.time() - t0) * 1000)
            bars = len(data) if data else 0
            result['data_bars'] = bars
            result['latency_ms'] = latency
            result['ok'] = bars >= MIN_BARS
            api.disconnect()
    except Exception:
        try:
            api.disconnect()
        except Exception:
            pass

    return result


def main():
    print("=" * 60)
    print("TDX 服务器测速开始")
    print("=" * 60)

    try:
        from pytdx.hq import TdxHq_API
    except Exception as e:
        print(f"[错误] pytdx 未安装或导入失败: {e}")
        return

    servers = get_candidate_servers()
    print(f"候选服务器: {len(servers)} 个")
    print(f"测试标的: {TEST_SYMBOL} (1分钟K线), 至少{MIN_BARS}条算可用")
    print("-" * 60)

    results = []
    for idx, srv in enumerate(servers, 1):
        r = test_server(TdxHq_API, srv)
        results.append(r)
        status = "OK " if r['ok'] else ("TCP" if r['tcp'] else "×  ")
        lat = f"{r['latency_ms']}ms" if r['latency_ms'] is not None else "-"
        print(f"  [{idx:>2}/{len(servers)}] {status} {r['ip']}:{r['port']} "
              f"bars={r['data_bars']} {lat}")

    # 筛选可用（能拉到数据），按延迟升序
    usable = [r for r in results if r['ok']]
    usable.sort(key=lambda x: x['latency_ms'])

    print("-" * 60)
    print(f"总候选: {len(servers)} | TCP通: {sum(1 for r in results if r['tcp'])} "
          f"| 能拉数据: {len(usable)}")

    # 取前15个写入配置
    top = usable[:15]
    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'test_symbol': TEST_SYMBOL,
        'total_candidates': len(servers),
        'tcp_ok': sum(1 for r in results if r['tcp']),
        'data_ok': len(usable),
        'servers': [{'ip': r['ip'], 'port': r['port'],
                     'latency_ms': r['latency_ms'], 'name': r['name']} for r in top]
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"可用服务器 TOP{len(top)} (按延迟):")
    for r in top:
        print(f"  {r['ip']}:{r['port']}  {r['latency_ms']}ms")
    print("=" * 60)
    print(f"结果已写入: {OUT_JSON}")

    # 短结论行（ASCII，保证可读）
    lat_min = top[0]['latency_ms'] if top else -1
    print(f"VERDICT candidates={len(servers)} tcp_ok={output['tcp_ok']} "
          f"data_ok={len(usable)} best_latency={lat_min}")

    # 额外写一个纯ASCII短摘要文件，便于读取
    summary_dir = r'C:\Users\win10_zq\.stepclaw\workspace-main-3'
    try:
        with open(os.path.join(summary_dir, 'tdx_refresh_verdict.txt'), 'w', encoding='ascii') as f:
            f.write(f"candidates={len(servers)} tcp_ok={output['tcp_ok']} "
                    f"data_ok={len(usable)} best_latency={lat_min}")
    except Exception:
        pass


if __name__ == '__main__':
    main()
