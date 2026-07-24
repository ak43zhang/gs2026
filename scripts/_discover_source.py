# -*- coding: utf-8 -*-
"""
数据源自动发现脚本：扫描 monitor_bond.py 及其依赖，找出TDX/行情数据源配置。
只读分析，不改动任何原代码。结果写入 discover_result.txt
"""
import os
import re

OUT = open('discover_result.txt', 'w', encoding='utf-8')

def log(s=''):
    OUT.write(str(s) + '\n')
    OUT.flush()

# ============ 1. 扫描 monitor_bond.py 的 import 和数据获取 ============
mb_path = 'src/gs2026/monitor/monitor_bond.py'
log('=' * 60)
log('1. monitor_bond.py 的 import 语句')
log('=' * 60)
with open(mb_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, l in enumerate(lines, 1):
    ls = l.strip()
    if ls.startswith('import ') or ls.startswith('from '):
        log(f'{i}: {ls}')

# ============ 2. 找数据获取相关关键词 ============
log('')
log('=' * 60)
log('2. 数据获取/行情/IP/服务器相关行')
log('=' * 60)
kws = ['tdx', 'fetch', 'get_data', 'quote', 'hq', 'ip', 'server', 'host',
       'port', 'connect', '行情', '采集', '数据源', 'client', 'pool',
       'realtime', 'snapshot', 'get_bond', 'get_stock', 'redis', 'akshare',
       'adata', 'efinance', 'mootdx', 'baostock', 'ths', 'eastmoney']
for i, l in enumerate(lines, 1):
    low = l.lower()
    for kw in kws:
        if kw in low and not l.strip().startswith('#'):
            log(f'{i}: {l.rstrip()[:110]}')
            break

OUT.close()
print('DONE')
