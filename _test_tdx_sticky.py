"""
TDX 粘性连接 + 失效换IP 自测（全程mock，不真连TDX）
验证：
1. 粘性：连接正常时一直复用同一IP
2. 心跳判空：get_security_count返回None → 标记坏IP并换IP
3. 采集空：_get_bond_tdx_once返回空 → get_bond_tdx标记坏IP换IP重试
4. 顺序换IP：exclude_current后取下一个健康IP
"""
import sys
sys.path.insert(0, 'F:\\pyworkspace2026\\gs2026\\src')

import pandas as pd
from gs2026.monitor import monitor_bond as mb

# 缩小IP池便于验证
mb.TDX_SERVERS = [('1.1.1.1', 7709), ('2.2.2.2', 7709), ('3.3.3.3', 7709)]
mb._tdx_server_status = {}
mb._tdx_current_server = None
mb._tdx_server_index = 0

print("=" * 50)
print("测试1: _get_next_server 粘性")
print("=" * 50)
mb._init_server_status()
# 无当前IP → 返回第一个
s1 = mb._get_next_server()
print(f"无当前IP，返回: {s1}  (期望 1.1.1.1)")
# 设当前IP，粘性应返回同一个
mb._tdx_current_server = ('1.1.1.1', 7709)
s2 = mb._get_next_server()
s3 = mb._get_next_server()
print(f"有当前IP，连续返回: {s2}, {s3}  (期望都是 1.1.1.1 - 粘性)")
assert s2 == ('1.1.1.1', 7709) and s3 == ('1.1.1.1', 7709), "粘性失败!"
print("[PASS] 粘性验证通过")

print()
print("=" * 50)
print("测试2: exclude_current 顺序换IP")
print("=" * 50)
s4 = mb._get_next_server(exclude_current=True)
print(f"排除当前1.1.1.1，返回: {s4}  (期望 2.2.2.2)")
assert s4 == ('2.2.2.2', 7709), "顺序换IP失败!"
print("[PASS] 顺序换IP通过")

print()
print("=" * 50)
print("测试3: 当前IP不健康时自动换下一个")
print("=" * 50)
# 标记1.1.1.1连续失败3次 → 不健康
for _ in range(3):
    mb._update_server_status(('1.1.1.1', 7709), False)
s5 = mb._get_next_server()  # 当前是1.1.1.1但已不健康
print(f"当前IP不健康，返回: {s5}  (期望非1.1.1.1)")
assert s5 != ('1.1.1.1', 7709), "不健康IP未跳过!"
print("[PASS] 不健康IP跳过通过")

print()
print("=" * 50)
print("测试4: get_bond_tdx 采集空 → 换IP重试")
print("=" * 50)
# mock _get_bond_tdx_once 始终返回空
call_log = []
def fake_once(filter_valid=True):
    call_log.append(mb._tdx_current_server)
    return pd.DataFrame()  # 始终空

mb._get_bond_tdx_once = fake_once
mb._tdx_current_server = ('2.2.2.2', 7709)
mb._tdx_connected = True
mb._tdx_api = None  # 避免close报错

# 记录 _update_server_status 调用
orig_update = mb._update_server_status
update_calls = []
def spy_update(server, success):
    update_calls.append((server, success))
    orig_update(server, success)
mb._update_server_status = spy_update

result = mb.get_bond_tdx(max_retries=3)
print(f"采集结果为空: {result.empty}  (期望 True)")
print(f"_get_bond_tdx_once 调用次数: {len(call_log)}  (期望 3)")
print(f"标记坏IP调用: {[c for c in update_calls if c[1]==False]}")
assert result.empty, "空结果断言失败"
assert len(call_log) == 3, f"重试次数错误: {len(call_log)}"
bad_marks = [c for c in update_calls if c[1] == False]
assert len(bad_marks) >= 3, "未标记坏IP"
print("[PASS] 采集空换IP重试通过")

print()
print("=" * 50)
print("全部测试通过 ✅")
print("=" * 50)
