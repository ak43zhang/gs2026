# -*- coding: utf-8 -*-
"""
修改 monitor_bond.py - 第二步实施（v3：正确变量名 TDX_SERVERS）
"""
import os

MB = r'F:\pyworkspace2026\gs2026\src\gs2026\monitor\monitor_bond.py'
BAK = MB + '.bak.3'

with open(MB, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

with open(BAK, 'w', encoding='utf-8', errors='ignore') as f:
    f.writelines(lines)

# 查找 TDX_SERVERS 定义行
tdx_line = None
for i, line in enumerate(lines):
    if line.strip().startswith('TDX_SERVERS') and '=' in line and '[' in line:
        tdx_line = i
        break

if tdx_line is None:
    print("ERR_NO_TDX_SERVERS")
    exit(1)

# 构造插入内容
LOADER = [
    '# ====== TDX Servers Loader (auto-refresh from config) ======\n',
    'import json\n',
    'import os as _os\n',
    '\n',
    'def _load_tdx_servers():\n',
    '    """Load fresh TDX servers from config/tdx_ips.json"""\n',
    '    cfg_path = _os.path.join(\n',
    '        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),\n',
    "        'config', 'tdx_ips.json'\n",
    '    )\n',
    '    try:\n',
    '        with open(cfg_path, "r", encoding="utf-8") as f:\n',
    '            cfg = json.load(f)\n',
    '        srvs = cfg.get("servers", [])\n',
    '        if srvs:\n',
    '            # Convert to (ip, port) tuples\n',
    '            return [(s["ip"], s["port"]) for s in srvs[:15]]\n',
    '    except Exception:\n',
    '        pass\n',
    '    return None\n',
    '\n',
    '_TDX_DYNAMIC = _load_tdx_servers()\n',
    'if _TDX_DYNAMIC is not None:\n',
    '    TDX_SERVERS = _TDX_DYNAMIC\n',
    'else:\n',
    '    # Use hardcoded TDX_SERVERS below\n',
    '    pass\n',
    '\n',
]

# 插入：在 TDX_SERVERS 行之前插入 loader
new_lines = lines[:tdx_line] + LOADER + ['# [Original TDX_SERVERS as fallback]\n'] + lines[tdx_line:]

with open(MB, 'w', encoding='utf-8', errors='ignore') as f:
    f.writelines(new_lines)

print(f"OK_TDX_LINE_{tdx_line}")
