# -*- coding: utf-8 -*-
"""极简数据源探测：只输出最关键信息，分块写小文件"""
import os

mb = 'src/gs2026/monitor/monitor_bond.py'
with open(mb, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# 只提取 import 行
imports = []
for i, l in enumerate(lines, 1):
    s = l.strip()
    if s.startswith('import ') or s.startswith('from '):
        imports.append(f'{i}:{s}')

with open('C:/Users/win10_zq/.stepclaw/workspace-main-3/imp.txt', 'w', encoding='utf-8') as o:
    o.write('\n'.join(imports))

print('IMPORTS', len(imports))
