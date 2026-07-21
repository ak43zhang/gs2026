import sys
sys.path.insert(0, 'src')
from gs2026.utils import config_util
from sqlalchemy import text

engine = config_util.get_engine()
conn = engine.connect()

# 盛德转债今天的数据
r = conn.execute(text("SELECT bond_code, bond_name, COUNT(*) cnt, MIN(time) t1, MAX(time) t2 FROM monitor_zq_sssj_20260720 WHERE bond_name LIKE '%盛德%' GROUP BY bond_code, bond_name"))
rows = r.fetchall()
print("今天盛德:", rows)

# Redis状态
from gs2026.utils import redis_util
redis_util.init_redis(host=config_util.get_config('common.redis.host'), port=config_util.get_config('common.redis.port'), decode_responses=False)
rc = redis_util._get_redis_client()
print("Redis ts 20260720:", rc.llen("monitor_zq_sssj_20260720:timestamps"))
print("Redis ts 20260717:", rc.llen("monitor_zq_sssj_20260717:timestamps"))
latest = rc.lindex("monitor_zq_sssj_20260720:timestamps", 0)
print("今天最新ts:", latest)

conn.close()
