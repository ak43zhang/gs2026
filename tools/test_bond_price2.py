import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util

# 先初始化 Redis
redis_util.init_redis(host='localhost', port=6379, decode_responses=False)

# 然后导入函数
from gs2026.dashboard2.routes.monitor import _get_bond_change_pct_batch

# 测试 10:29:06
try:
    result = _get_bond_change_pct_batch('20260518', '10:29:06', ['110072', '110073', '110074'])
    print(f"Result type: {type(result)}")
    print(f"Result sample: {list(result.items())[:3] if result else 'empty'}")
    
    if result:
        first_key = list(result.keys())[0]
        first_val = result[first_key]
        print(f"First value type: {type(first_val)}")
        print(f"First value: {first_val}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
