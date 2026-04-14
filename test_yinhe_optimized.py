import sys
sys.path.insert(0, 'src')
import time

from gs2026.monitor.monitor_bond_yinhe_test import get_bond_yinhe, init_bond_meta

# 测试初始化
print('初始化债券基础信息...')
init_bond_meta()

# 测试获取100只债券（默认）
print('\n测试获取100只债券...')
start = time.time()
df = get_bond_yinhe(max_bonds=100)
elapsed = time.time() - start
print(f'获取完成: {len(df)} 只, 耗时 {elapsed*1000:.1f}ms')

if not df.empty:
    print(f'字段: {df.columns.tolist()}')
    print(f'\n前3条数据:')
    print(df.head(3).to_string())
else:
    print("数据为空，可能需要检查API连接")
