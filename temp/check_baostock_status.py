#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 Baostock 接口状态"""
import sys
import time
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

import baostock as bs
from loguru import logger

print("=" * 70)
print("Baostock 接口状态检查")
print("=" * 70)

# 1. 登录测试
print("\n【1】登录测试")
start = time.time()
lg = bs.login()
login_time = time.time() - start

print(f"登录耗时: {login_time:.3f}秒")
print(f"登录状态: {lg.error_code} - {lg.error_msg}")

if lg.error_code != '0':
    print("❌ 登录失败，可能是接口问题")
    sys.exit(1)

# 2. 查询单只股票测试
print("\n【2】单只股票查询测试")
test_codes = ['sh.600000', 'sz.000001', 'sh.600519']

for code in test_codes:
    start = time.time()
    rs = bs.query_history_k_data_plus(
        code=code,
        fields="code,date,open,close,high,low,volume,amount",
        start_date='2026-03-25',
        end_date='2026-03-30',
        frequency="d",
        adjustflag="3"
    )
    query_time = time.time() - start
    
    data_count = 0
    while rs.error_code == '0' and rs.next():
        data_count += 1
    
    status = "✅" if rs.error_code == '0' else "❌"
    print(f"{status} {code}: 耗时{query_time:.3f}秒, 返回{data_count}条, 状态={rs.error_code}")

# 3. 并发查询测试
print("\n【3】并发查询压力测试")
import concurrent.futures

def query_single(code):
    start = time.time()
    rs = bs.query_history_k_data_plus(
        code=code,
        fields="code,date,open,close,high,low,volume,amount",
        start_date='2026-03-25',
        end_date='2026-03-30',
        frequency="d",
        adjustflag="3"
    )
    elapsed = time.time() - start
    return code, elapsed, rs.error_code

# 测试10只股票的并发查询
test_codes_10 = ['sh.600000', 'sz.000001', 'sh.600519', 'sz.000858', 'sh.601318',
                 'sz.002415', 'sh.600036', 'sz.000002', 'sh.601012', 'sz.300750']

start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(query_single, code) for code in test_codes_10]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]
total_time = time.time() - start

success_count = sum(1 for _, _, err in results if err == '0')
avg_time = sum(t for _, t, _ in results) / len(results)

print(f"并发查询10只股票:")
print(f"  总耗时: {total_time:.3f}秒")
print(f"  平均单只: {avg_time:.3f}秒")
print(f"  成功率: {success_count}/10")

# 4. 检查 Baostock 版本
print("\n【4】Baostock 版本信息")
print(f"Baostock 版本: {bs.__version__ if hasattr(bs, '__version__') else '未知'}")

# 5. 网络延迟测试
print("\n【5】网络延迟测试")
import socket

def check_host(host, port=80):
    try:
        start = time.time()
        socket.create_connection((host, port), timeout=5)
        return time.time() - start
    except:
        return None

hosts = ['www.baostock.com', 'query.sse.com.cn', 'www.szse.cn']
for host in hosts:
    latency = check_host(host)
    if latency:
        print(f"  {host}: {latency*1000:.1f}ms")
    else:
        print(f"  {host}: 无法连接")

# 登出
bs.logout()

print("\n" + "=" * 70)
print("检查完成")
print("=" * 70)
