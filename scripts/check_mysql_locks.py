import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.utils import config_util
from sqlalchemy import create_engine, text

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 查看正在等待锁或运行超60秒的事务
    r = conn.execute(text("SELECT trx_id, trx_state, trx_started, trx_query FROM information_schema.INNODB_TRX"))
    rows = r.fetchall()
    print(f'活跃事务: {len(rows)}')
    for row in rows:
        print(f'  id={row[0]}, state={row[1]}, started={row[2]}, query={str(row[3])[:120] if row[3] else "None"}')
    
    # 查看innodb_lock_wait_timeout
    r2 = conn.execute(text("SELECT @@innodb_lock_wait_timeout"))
    print(f'\ninnodb_lock_wait_timeout: {r2.scalar()}秒')
    
    # 查看当前进程列表中长时间运行的
    r3 = conn.execute(text("SELECT id, user, time, state, LEFT(info, 100) as info FROM information_schema.processlist WHERE time > 30 ORDER BY time DESC"))
    rows3 = r3.fetchall()
    print(f'\n运行超30秒的进程: {len(rows3)}')
    for row in rows3:
        print(f'  id={row[0]}, user={row[1]}, time={row[2]}s, state={row[3]}, sql={row[4]}')
