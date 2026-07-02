"""查看并KILL stock_anomaly相关锁"""
from sqlalchemy import text
from gs2026.utils import config_util

engine = config_util.get_engine()

with engine.connect() as conn:
    # 1. 查看活跃事务
    print("=== 活跃事务 ===")
    result = conn.execute(text("""
        SELECT trx_id, trx_state, trx_started, trx_mysql_thread_id, 
               trx_query, trx_rows_locked, trx_rows_modified
        FROM information_schema.innodb_trx
        ORDER BY trx_started ASC
    """))
    rows = result.fetchall()
    if rows:
        for r in rows:
            print(f"  线程={r[3]} 状态={r[1]} 开始={r[2]} 锁行={r[5]} 改行={r[6]}")
            print(f"    SQL: {str(r[4])[:120]}")
    else:
        print("  无活跃事务")

    # 2. 查看相关进程
    print("\n=== 相关进程 ===")
    result = conn.execute(text("""
        SELECT id, user, host, db, command, time, state, LEFT(info, 120) as info
        FROM information_schema.processlist
        WHERE info LIKE '%stock_anomaly%' 
           OR state LIKE '%lock%'
           OR state LIKE '%Waiting%'
        ORDER BY time DESC
    """))
    rows = result.fetchall()
    kill_ids = []
    if rows:
        for r in rows:
            print(f"  ID={r[0]} time={r[5]}s state={r[6]} cmd={r[4]}")
            print(f"    SQL: {r[7]}")
            # 收集需要kill的连接（排除当前连接）
            if r[5] and int(r[5]) > 30:  # 超过30秒的
                kill_ids.append(r[0])
    else:
        print("  无相关进程")

    # 3. KILL阻塞连接
    if kill_ids:
        print(f"\n=== 准备KILL {len(kill_ids)} 个阻塞连接 ===")
        for pid in kill_ids:
            try:
                conn.execute(text(f"KILL {pid}"))
                print(f"  KILLED: {pid}")
            except Exception as e:
                print(f"  KILL {pid} 失败: {e}")
        conn.commit()
        print("完成!")
    else:
        print("\n无需KILL的连接")
