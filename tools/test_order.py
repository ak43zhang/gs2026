import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import redis_util

# 先初始化 Redis
redis_util.init_redis(host='localhost', port=6379, decode_responses=False)
print(f"After first init: {redis_util._redis_client}")

# 然后导入函数 - 这会触发 DataService 初始化
from gs2026.dashboard2.routes.monitor import _get_bond_change_pct_batch

print(f"After import: {redis_util._redis_client}")

# 现在直接检查 _get_bond_change_pct_batch 内部的行为
sssj_table = "monitor_zq_sssj_20260518"
time_str = "10:29:06"
redis_key = f"{sssj_table}:{time_str}"

df = redis_util.load_dataframe_by_key(redis_key, use_compression=False)
print(f"df columns: {list(df.columns) if df is not None else 'None'}")
print(f"'price' in df.columns: {'price' in df.columns if df is not None else 'N/A'}")

# 调用函数
result = _get_bond_change_pct_batch('20260518', '10:29:06', ['110072', '110073', '110074'])
print(f"Result type: {type(result)}")
print(f"Result sample: {list(result.items())[:3] if result else 'empty'}")
