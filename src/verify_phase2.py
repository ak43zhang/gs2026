"""优化版：避免窗口函数，用 LIMIT/OFFSET 替代"""
from sqlalchemy import create_engine, text
import time

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs',
                       pool_size=1, connect_args={'connect_timeout': 5})

with engine.connect() as conn:
    # === 方案1：Python 计算（取160行，Python求均值）===
    t0 = time.time()
    rows = conn.execute(text(
        "SELECT body_up, body_down, min_up, min_down "
        "FROM monitor_gp_apqd_20260526 ORDER BY time DESC LIMIT 160"
    )).fetchall()
    
    recent = rows[:60]   # 最近3分钟
    ref = rows[60:160]   # 参照5分钟
    
    def safe_ratio(up, down):
        total = up + down
        return up / total if total > 0 else None
    
    def avg_ratios(data, fn):
        vals = [fn(r) for r in data if fn(r) is not None]
        return sum(vals) / len(vals) if vals else None
    
    recent_body = avg_ratios(recent, lambda r: safe_ratio(r[0], r[1]))
    recent_tick = avg_ratios(recent, lambda r: safe_ratio(r[2], r[3]))
    ref_body = avg_ratios(ref, lambda r: safe_ratio(r[0], r[1]))
    ref_tick = avg_ratios(ref, lambda r: safe_ratio(r[2], r[3]))
    current_body = safe_ratio(rows[0][0], rows[0][1]) if rows else None
    
    elapsed1 = (time.time() - t0) * 1000
    print(f"方案1 Python计算: {elapsed1:.1f}ms")
    print(f"  recent_body={recent_body:.6f}, recent_tick={recent_tick:.6f}")
    print(f"  ref_body={ref_body:.6f}, ref_tick={ref_tick:.6f}")
    print(f"  current_body={current_body:.6f}")
    
    # === 方案2：纯SQL LIMIT/OFFSET（无窗口函数）===
    t0 = time.time()
    result = conn.execute(text("""
        SELECT 
          (SELECT AVG(body_up * 1.0 / NULLIF(body_up + body_down, 0))
           FROM (SELECT body_up, body_down FROM monitor_gp_apqd_20260526 
                 ORDER BY time DESC LIMIT 60) r) as recent_body,
          (SELECT AVG(min_up * 1.0 / NULLIF(min_up + min_down, 0))
           FROM (SELECT min_up, min_down FROM monitor_gp_apqd_20260526 
                 ORDER BY time DESC LIMIT 60) r) as recent_tick,
          (SELECT AVG(body_up * 1.0 / NULLIF(body_up + body_down, 0))
           FROM (SELECT body_up, body_down FROM monitor_gp_apqd_20260526 
                 ORDER BY time DESC LIMIT 100 OFFSET 60) r) as ref_body,
          (SELECT AVG(min_up * 1.0 / NULLIF(min_up + min_down, 0))
           FROM (SELECT min_up, min_down FROM monitor_gp_apqd_20260526 
                 ORDER BY time DESC LIMIT 100 OFFSET 60) r) as ref_tick,
          (SELECT body_up * 1.0 / NULLIF(body_up + body_down, 0)
           FROM monitor_gp_apqd_20260526 ORDER BY time DESC LIMIT 1) as current_body
    """)).fetchone()
    elapsed2 = (time.time() - t0) * 1000
    print(f"\n方案2 纯SQL: {elapsed2:.1f}ms")
    print(f"  recent_body={result[0]:.6f}, recent_tick={result[1]:.6f}")
    print(f"  ref_body={result[2]:.6f}, ref_tick={result[3]:.6f}")
    print(f"  current_body={result[4]:.6f}")
    
    # === 方案3：原始窗口函数（对比）===
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
    elapsed3 = (time.time() - t0) * 1000
    print(f"\n方案3 窗口函数: {elapsed3:.1f}ms")
    
    print(f"\n=== 性能对比 ===")
    print(f"  方案1 Python:    {elapsed1:.1f}ms")
    print(f"  方案2 纯SQL:     {elapsed2:.1f}ms")
    print(f"  方案3 窗口函数:  {elapsed3:.1f}ms")
