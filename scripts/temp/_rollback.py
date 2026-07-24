"""
回滚：清除盛德转债和三江转债在MySQL和Redis中的所有脏数据
让monitor从现在开始重新写入正确数据
"""
import sys
sys.path.insert(0, 'src')
from gs2026.utils import config_util, redis_util
from sqlalchemy import text

# 初始化
redis_util.init_redis(
    host=config_util.get_config('common.redis.host'),
    port=config_util.get_config('common.redis.port'),
    decode_responses=False
)
r = redis_util._get_redis_client()
engine = config_util.get_engine()

BONDS = {'118058': '盛德转债', '123273': '三江转债'}
TODAY = '20260720'
TABLE = f'monitor_zq_sssj_{TODAY}'

print("=" * 50)
print("1. 清除MySQL中的脏数据")
print("=" * 50)

with engine.connect() as conn:
    for code, name in BONDS.items():
        cnt = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE} WHERE bond_code = :code"), {'code': code}).scalar()
        conn.execute(text(f"DELETE FROM {TABLE} WHERE bond_code = :code"), {'code': code})
        print(f"  {name}({code}): 删除 {cnt} 条")
    conn.commit()
    print("  COMMITTED")

print()
print("=" * 50)
print("2. 清除Redis中的脏数据")
print("=" * 50)

for code, name in BONDS.items():
    key = f"bond:tick:{code}:{TODAY}"
    existed = r.exists(key)
    if existed:
        count = r.hlen(key)
        r.delete(key)
        print(f"  DEL {key} ({count}条)")
    else:
        print(f"  {key} 不存在，无需清理")

print()
print("=" * 50)
print("3. 验证清理结果")
print("=" * 50)

with engine.connect() as conn:
    for code, name in BONDS.items():
        cnt = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE} WHERE bond_code = :code"), {'code': code}).scalar()
        redis_cnt = r.hlen(f"bond:tick:{code}:{TODAY}")
        print(f"  {name}({code}): MySQL={cnt}条, Redis={redis_cnt}条")

print()
print("DONE. 两只债券数据已清空。")
print("monitor正在运行，会从下一个tick开始重新写入正确的实时数据。")
print("大约等1-2分钟后刷新页面即可看到新数据。")
