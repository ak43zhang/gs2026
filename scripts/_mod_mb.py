# -*- coding: utf-8 -*-
"""
自动修改 monitor_bond.py：添加IP池动态加载（第二步实施）

修改内容：
1. 在 IP_POOL 定义前插入 _load_ip_pool() 函数
2. 将硬编码 IP_POOL = [...] 改为 IP_POOL = _load_ip_pool()
3. 保留原硬编码作为兜底（配置文件不存在时回退）

备份原文件到 monitor_bond.py.bak
"""
import os
import re

MB = r'F:\pyworkspace2026\gs2026\src\gs2026\monitor\monitor_bond.py'
BAK = MB + '.bak'

# 读取原文件
with open(MB, 'r', encoding='utf-8', errors='ignore') as f:
    original = f.read()

# 备份
with open(BAK, 'w', encoding='utf-8', errors='ignore') as f:
    f.write(original)

# 要插入的 loader 函数（纯ASCII，避免编码问题）
LOADER = '''
# ====== IP Pool Loader (auto-refresh from config) ======
import json
import os as _os

def _load_ip_pool():
    """
    Load IP pool from config/tdx_ips.json (refreshed by refresh_tdx_ips.py)
    Falls back to hardcoded pool if config missing or empty.
    """
    config_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        'config', 'tdx_ips.json'
    )
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        srv = cfg.get('servers', [])
        if srv:
            # Convert to (ip, port, weight) format, weight=1 for all
            return [(s['ip'], s['port'], 1) for s in srv[:15]]
    except Exception:
        pass
    # Fallback: return None to signal using hardcoded below
    return None

# Try dynamic pool first, fallback to hardcoded
_IP_POOL_DYNAMIC = _load_ip_pool()

'''

# 查找 IP_POOL = [ 的位置
match = re.search(r'^(IP_POOL\s*=\s*\[)', original, re.MULTILINE)
if not match:
    print("ERROR: Cannot find IP_POOL definition")
    exit(1)

ip_pool_start = match.start()

# 构造新内容：loader + 条件IP_POOL
new_content = original[:ip_pool_start] + LOADER + \
    '''if _IP_POOL_DYNAMIC is not None:
    IP_POOL = _IP_POOL_DYNAMIC
else:
    # Fallback to hardcoded (original pool below)
    ''' + original[ip_pool_start:]

# 写回
with open(MB, 'w', encoding='utf-8', errors='ignore') as f:
    f.write(new_content)

print("MODIFIED_OK")
print(f"Backup: {BAK}")
print(f"Lines: {len(original.splitlines())} -> {len(new_content.splitlines())}")
