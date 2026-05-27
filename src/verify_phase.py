"""验证 apqd 表结构和数据"""
from sqlalchemy import create_engine, text

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs',
                       pool_size=1, connect_args={'connect_timeout': 5})

with engine.connect() as conn:
    # 1. 表结构
    cols = conn.execute(text("SHOW COLUMNS FROM monitor_gp_apqd_20260526")).fetchall()
    print("=== APQD 表字段 ===")
    for c in cols:
        print(f"  {c[0]:25s} {c[1]}")
    
    # 2. 数据量
    cnt = conn.execute(text("SELECT COUNT(*) FROM monitor_gp_apqd_20260526")).fetchone()
    print(f"\n总行数: {cnt[0]}")
    
    # 3. 最近5条数据
    rows = conn.execute(text(
        "SELECT time, body_up, body_down, min_up, min_down "
        "FROM monitor_gp_apqd_20260526 ORDER BY time DESC LIMIT 5"
    )).fetchall()
    print("\n=== 最近5条 ===")
    for r in rows:
        print(f"  time={r[0]}  body_up={r[1]}  body_down={r[2]}  min_up={r[3]}  min_down={r[4]}")
    
    # 4. 测试 SQL 聚合性能
    import time
    t0 = time.time()
    result = conn.execute(text("""
        SELECT 
          AVG(CASE WHEN rn <= 60 THEN body_up * 1.0 / NULLIF(body_up + body_down, 0) END) as recent_body,
          AVG(CASE WHEN rn <= 60 THEN min_up * 1.0 / NULLIF(min_up + min_down, 0) END) as recent_tick,
          AVG(CASE WHEN rn > 60 THEN body_up * 1.0 / NULLIF(body_up + body_down, 0) END) as ref_body,
          AVG(CASE WHEN rn > 60 THEN min_up * 1.0 / NULLIF(min_up + min_down, 0) END) as ref_tick,
          MAX(CASE WHEN rn = 1 THEN body_up * 1.0 / NULLIF(body_up + body_down, 0) END) as current_body
        FROM (
          SELECT body_up, body_down, min_up, min_down,
                 ROW_NUMBER() OVER (ORDER BY time DESC) as rn
          FROM monitor_gp_apqd_20260526
          LIMIT 160
        ) t
    """)).fetchone()
    elapsed = (time.time() - t0) * 1000
    
    print(f"\n=== SQL 聚合结果（耗时 {elapsed:.1f}ms）===")
    print(f"  recent_body = {result[0]}")
    print(f"  recent_tick = {result[1]}")
    print(f"  ref_body    = {result[2]}")
    print(f"  ref_tick    = {result[3]}")
    print(f"  current_body= {result[4]}")
    
    # 5. 计算阶段
    if result[0] and result[2] and result[4] is not None:
        momentum = (float(result[0]) - float(result[2])) * 0.6 + (float(result[1]) - float(result[3])) * 0.4
        current_state = 'bull' if float(result[4]) > 0.5 else 'bear'
        trend = 'improving' if momentum > 0 else 'weakening'
        
        if current_state == 'bull' and trend == 'improving': phase = '上升'
        elif current_state == 'bull' and trend == 'weakening': phase = '回落'
        elif current_state == 'bear' and trend == 'improving': phase = '反弹'
        else: phase = '下降'
        
        abs_m = abs(momentum)
        if abs_m < 0.005: phase = '震荡'
        strength = '强' if abs_m > 0.05 else ('中' if abs_m > 0.02 else '弱')
        
        print(f"\n=== 阶段判断 ===")
        print(f"  current_body = {float(result[4]):.4f} → {current_state}")
        print(f"  momentum = {momentum:.6f} → {trend}")
        print(f"  阶段: {phase}({strength})")
