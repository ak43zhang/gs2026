# -*- coding: utf-8 -*-
"""
修改 monitor_bond.py - 第二步实施（v2：行号硬定位，更可靠）
"""
import os

MB = r'F:\pyworkspace2026\gs2026\src\gs2026\monitor\monitor_bond.py'
BAK = MB + '.bak.2'

# 读取
with open(MB, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# 备份
with open(BAK, 'w', encoding='utf-8', errors='ignore') as f:
    f.writelines(lines)

# 查找 IP_POOL 定义行（找 "IP_POOL" 开头的行）
ip_pool_line = None
for i, line in enumerate(lines):
    if line.strip().startswith('IP_POOL') and '=' in line:
        ip_pool_line = i
        break

if ip_pool_line is None:
    print("ERR_NO_IP_POOL")
    exit(1)

# 构造插入内容（loader函数）
LOADER_LINES = [
    '# ====== IP Pool Loader (auto-refresh from config) ======\n',
    'import json\n',
    'import os as _os\n',
    '\n',
    'def _load_ip_pool():\n',
    '    config_path = _os.path.join(\n',
    '        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),\n',
    "        'config', 'tdx_ips.json'\n",
    '    )\n',
    '    try:\n',
    '        with open(config_path, "r", encoding="utf-8") as f:\n',
    '            cfg = json.load(f)\n',
    '        srv = cfg.get("servers", [])\n',
    '        if srv:\n',
    '            return [(s["ip"], s["port"], 1) for s in srv[:15]]\n',
    '    except Exception:\n',
    '        pass\n',
    '    return None\n',
    '\n',
    '_IP_POOL_DYNAMIC = _load_ip_pool()\n',
    'if _IP_POOL_DYNAMIC is not None:\n',
    '    IP_POOL = _IP_POOL_DYNAMIC\n',
    'else:\n',
    '    # Fallback to hardcoded below\n',
    '    pass\n',
    '\n',
]

# 插入：在 IP_POOL 行之前插入 loader，然后注释掉原来的 IP_POOL 行
new_lines = lines[:ip_pool_line] + LOADER_LINES + ['# [Original IP_POOL kept as fallback]\n'] + lines[ip_pool_line:]

# 写回
with open(MB, 'w', encoding='utf-8', errors='ignore') as f:
    f.writelines(new_lines)

print(f"OK_LINE_{ip_pool_line}_NEW_{len(new_lines)}_OLD_{len(lines)}")
