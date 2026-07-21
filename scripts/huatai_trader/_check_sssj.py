"""检查分时数据表状态"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.utils import config_util
from sqlalchemy import text

engine = config_util.get_engine()

with engine.connect() as conn:
    # 1. 今天表是否存在、有多少数据
    try:
        r = conn.execute(text('SELECT COUNT(*) FROM monitor_zq_sssj_20260720'))
        print(f'monitor_zq_sssj_20260720 总条数: {r.scalar()}')
    except Exception as e:
        print(f'20260720表: {e}')

    # 2. 盛德转债在今天表中?
    try:
        r = conn.execute(text(
            "SELECT bond_code, bond_name, COUNT(*) as cnt, MIN(time) as t1, MAX(time) as t2 "
            "FROM monitor_zq_sssj_20260720 "
            "WHERE bond_name LIKE '%盛德%' OR bond_code='118058' "
            "GROUP BY bond_code, bond_name"
        ))
        rows = r.fetchall()
        if rows:
            for row in rows:
                print(f'今天盛德: {row}')
        else:
            print('盛德转债今天无数据')
    except Exception as e:
        print(f'查询失败: {e}')

    # 3. 0717表中盛德转债
    try:
        r = conn.execute(text(
            "SELECT bond_code, bond_name, COUNT(*) as cnt "
            "FROM monitor_zq_sssj_20260717 "
            "WHERE bond_name LIKE '%盛德%' OR bond_code='118058' "
            "GROUP BY bond_code, bond_name"
        ))
        rows = r.fetchall()
        if rows:
            for row in rows:
                print(f'0717盛德: {row}')
    except Exception as e:
        print(f'0717查询: {e}')

    # 4. Redis中bond:tick缓存状态
    try:
        from gs2026.utils import redis_util
        redis_util.init_redis(
            host=config_util.get_config('common.redis.host'),
            port=config_util.get_config('common.redis.port'),
            decode_responses=False
        )
        r_client = redis_util._get_redis_client()
        
        # 检查today的timestamps
        ts_key_today = "monitor_zq_sssj_20260720:timestamps"
        ts_key_old = "monitor_zq_sssj_20260717:timestamps"
        
        ts_today = r_client.llen(ts_key_today)
        ts_old = r_client.llen(ts_key_old)
        print(f'\nRedis timestamps: 20260720={ts_today}条, 20260717={ts_old}条')
        
        # 检查bond:tick缓存
        tick_today = r_client.exists('bond:tick:118058:20260720')
        tick_old = r_client.exists('bond:tick:118058:20260717')
        print(f'Redis bond:tick:118058: 20260720存在={tick_today}, 20260717存在={tick_old}')
        
        # 今天最新时间戳
        if ts_today > 0:
            latest = r_client.lindex(ts_key_today, 0)
            print(f'今天最新时间戳: {latest}')
            
    except Exception as e:
        print(f'Redis检查: {e}')
