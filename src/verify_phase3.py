"""检查索引并测试加索引后性能"""
from sqlalchemy import create_engine, text
import time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs',
                       pool_size=1, connect_args={'connect_timeout': 5})

with engine.connect() as conn:
    # 1. 检查现有索引
    indexes = conn.execute(text("SHOW INDEX FROM monitor_gp_apqd_20260526")).fetchall()
    print("=== 现有索引 ===")
    for idx in indexes:
        print(f"  {idx[2]}: column={idx[4]}, type={idx[10]}")
    
    if not any(idx[4] == 'time' for idx in indexes):
        print("\n[!] time 列无索引，添加中...")
        conn.execute(text("CREATE INDEX idx_time ON monitor_gp_apqd_20260526 (time)"))
        conn.commit()
        print("[OK] 索引已创建")
    else:
        print("\n[OK] time 列已有索引")
    
    # 2. 重新测试性能（3次取平均）
    times = []
    for i in range(3):
        t0 = time.time()
        conn.execute(text("""
            SELECT 
              AVG(CASE WHEN rn <= 60 THEN body_up * 1.0 / NULLIF(body_up + body_down, 0) END),
              AVG(CASE WHEN rn <= 60 THEN min_up * 1.0 / NULLIF(min_up + min_down, 0) END),
              AVG(CASE WHEN rn > 60 THEN body_up * 1.0 / NULLIF(body_up + body_down, 0) END),
              AVG(CASE WHEN rn > 60 THEN min_up * 1.0 / NULLIF(min_up + min_down, 0) END),
              MAX(CASE WHEN rn = 1 THEN body_up * 1.0 / NULLIF(body_up + body_down, 0) END)
            FROM (
              SELECT body_up, body_down, min_up, min_down,
                     ROW_NUMBER() OVER (ORDER BY time DESC) as rn
              FROM monitor_gp_apqd_20260526
              LIMIT 160
            ) t
        """)).fetchone()
        elapsed = (time.time() - t0) * 1000
        times.append(elapsed)
        print(f"  Run {i+1}: {elapsed:.1f}ms")
    
    print(f"\n  平均: {sum(times)/len(times):.1f}ms")
    
    # 3. Python方案也测
    times2 = []
    for i in range(3):
        t0 = time.time()
        rows = conn.execute(text(
            "SELECT body_up, body_down, min_up, min_down "
            "FROM monitor_gp_apqd_20260526 ORDER BY time DESC LIMIT 160"
        )).fetchall()
        recent = rows[:60]
        ref = rows[60:]
        def sr(u,d): t=u+d; return u/t if t>0 else None
        def ar(data, fn): v=[fn(r) for r in data if fn(r) is not None]; return sum(v)/len(v) if v else None
        ar(recent, lambda r: sr(r[0],r[1]))
        ar(recent, lambda r: sr(r[2],r[3]))
        ar(ref, lambda r: sr(r[0],r[1]))
        ar(ref, lambda r: sr(r[2],r[3]))
        elapsed = (time.time() - t0) * 1000
        times2.append(elapsed)
    
    print(f"  Python方案平均: {sum(times2)/len(times2):.1f}ms")
