import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

# 检查 gs2026.dashboard2.routes.monitor 实际加载的是哪个文件
import gs2026.dashboard2.routes.monitor as m
print(f'dashboard2 module file: {m.__file__}')

# 检查 _get_bond_change_pct_batch 的源代码
import inspect
print(inspect.getsource(m._get_bond_change_pct_batch))
